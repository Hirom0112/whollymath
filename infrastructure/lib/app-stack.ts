// AppStack — the backend (ECS Fargate + ALB) and the frontend (S3 + CloudFront).
//
// Architecture (CLAUDE.md §10, TECH_STACK §7):
//   - FastAPI runs as an ARM64 Fargate task behind a public ALB. ARM matches the
//     Graviton-priced Fargate platform and builds natively on the M-series dev host.
//   - Because NetworkStack sets natGateways:0, the task runs in PUBLIC subnets with a
//     public IP so it can pull from ECR and call the Anthropic API via the IGW.
//   - The frontend is a static Vite build in a private S3 bucket fronted by CloudFront.
//     CloudFront serves the SPA from S3 and routes the backend API path patterns to the
//     ALB origin, so the frontend's relative API calls work from one origin.
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as ecs_patterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface AppStackProps extends cdk.StackProps {
  readonly vpc: ec2.Vpc;
  readonly appSecurityGroup: ec2.SecurityGroup;
  readonly albSecurityGroup: ec2.SecurityGroup;
  readonly dbInstance: rds.DatabaseInstance;
  readonly dbSecret: secretsmanager.ISecret;
  readonly artifactBucket: s3.Bucket;
}

// The exact path patterns the frontend calls with relative URLs. CloudFront routes
// each of these to the ALB origin; everything else is served as the SPA from S3.
const API_PATH_PATTERNS: readonly string[] = [
  '/session',
  '/turn',
  '/units',
  '/unit/*',
  '/me',
  '/events',
  // Cached mascot-voice mp3s (Slice AR.3): the backend serves them as static files under
  // /tts/audio/*; a SpokenAudio.audio_url resolves here. Routed to the ALB like the rest (the
  // backend StaticFiles mount serves them) so the avatar can play a banked line in production.
  '/tts/*',
  '/hw/*',
  '/course',
  '/course/*',
  '/eval/*',
  '/routing-choices',
  '/teacher',
  '/teacher/*',
  '/health',
];

export class AppStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AppStackProps) {
    super(scope, id, props);

    // ---- API-key secrets. CDK creates the secret *shells* but does NOT manage their values
    // (no secretStringValue): the real keys are populated out-of-band via `put-secret-value`
    // after deploy, so subsequent `cdk deploy`s never clobber them back to a placeholder. Each
    // shell is born with an auto-generated random value that the operator overwrites.
    const anthropicSecret = new secretsmanager.Secret(this, 'AnthropicApiKey', {
      secretName: 'whollymath/anthropic-api-key',
      description: 'Anthropic API key; value set out-of-band post-deploy.',
    });
    const langsmithSecret = new secretsmanager.Secret(this, 'LangsmithApiKey', {
      secretName: 'whollymath/langsmith-api-key',
      description: 'LangSmith API key (LLM-call tracing); value set out-of-band post-deploy.',
    });
    const mathpixSecret = new secretsmanager.Secret(this, 'MathpixAppKey', {
      secretName: 'whollymath/mathpix-app-key',
      description: 'Mathpix app key (homework-scan OCR); value set out-of-band post-deploy.',
    });
    // HS256 signing key for our parent/child session JWTs (app/auth/tokens.py, Slice
    // auth/parent-child). Unlike the API-key shells above, the AUTO-GENERATED random value
    // is exactly what we want — a long random signing secret — so it needs NO out-of-band
    // population; it just must stay STABLE across deploys (existing sessions stay valid),
    // which a managed Secret does. Rotating it invalidates all live sessions (acceptable).
    const sessionSigningKey = new secretsmanager.Secret(this, 'SessionSigningKey', {
      secretName: 'whollymath/session-signing-key',
      description: 'HS256 signing key for parent/child session JWTs (random; keep stable).',
    });

    // ---- Backend: ECS cluster + ALB Fargate service.
    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc: props.vpc,
    });

    const image = ecs.ContainerImage.fromAsset('../backend', {
      file: 'Dockerfile',
      platform: ecr_assets.Platform.LINUX_ARM64,
    });

    // The ALB is built explicitly with the NetworkStack-owned ALB security group (rather
    // than letting the ecs_patterns construct generate one in this stack). Combined with
    // the intra-NetworkStack ALB->task ingress rule, this keeps every SG-to-SG rule out
    // of the cross-stack reference graph and avoids a dependency cycle. See NetworkStack.
    const loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc: props.vpc,
      internetFacing: true,
      securityGroup: props.albSecurityGroup,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    });

    const service = new ecs_patterns.ApplicationLoadBalancedFargateService(this, 'Service', {
      cluster,
      loadBalancer,
      cpu: 256,
      memoryLimitMiB: 512,
      desiredCount: 1,
      publicLoadBalancer: true,
      // Roll back automatically (and fail fast) if a deployment's tasks never reach healthy —
      // e.g. a failed `alembic upgrade head` on first boot — instead of stalling up to ~3h.
      circuitBreaker: { rollback: true },
      // Single-task demo: don't drop the one running task below the desired count mid-deploy.
      minHealthyPercent: 100,
      // The entrypoint runs `alembic upgrade head` before uvicorn binds, and the task fetches
      // its secrets at startup — so a new task isn't answerable for ~30-90s. Give it grace before
      // ALB health checks count against the deployment circuit breaker (a too-short window was
      // tripping a rollback on task-def changes even though the task came up healthy).
      healthCheckGracePeriod: cdk.Duration.seconds(120),
      // natGateways:0 → tasks need a public IP in a PUBLIC subnet to reach ECR + Anthropic.
      assignPublicIp: true,
      taskSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [props.appSecurityGroup],
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
      taskImageOptions: {
        image,
        containerPort: 8000,
        environment: {
          DB_PORT: '5432',
          DB_NAME: 'whollymath',
          // Non-secret LangSmith config; the API key rides in `secrets` below. Tracing is a
          // no-op passthrough unless LANGSMITH_TRACING=true AND a key is present (Slice PL.0).
          LANGSMITH_TRACING: 'true',
          LANGSMITH_PROJECT: 'whollymath',
          // Parent/child auth (Slice auth/parent-child). The COPPA verification email's SES
          // "From" identity + the public origin used to build the verification link. SES_SENDER
          // must be a VERIFIED SES identity (see AUTH.md runbook); until then the app uses its
          // logging fallback. SESSION_COOKIE_SECURE is intentionally unset → defaults true (prod
          // is HTTPS behind CloudFront), so the session cookie is Secure.
          SES_SENDER: 'no-reply@whollymath.app',
          AWS_REGION: this.region,
          PUBLIC_API_BASE_URL: 'https://whollymath.app',
        },
        secrets: {
          DB_HOST: ecs.Secret.fromSecretsManager(props.dbSecret, 'host'),
          DB_USER: ecs.Secret.fromSecretsManager(props.dbSecret, 'username'),
          DB_PASSWORD: ecs.Secret.fromSecretsManager(props.dbSecret, 'password'),
          ANTHROPIC_API_KEY: ecs.Secret.fromSecretsManager(anthropicSecret),
          LANGSMITH_API_KEY: ecs.Secret.fromSecretsManager(langsmithSecret),
          MATHPIX_APP_KEY: ecs.Secret.fromSecretsManager(mathpixSecret),
          SESSION_SIGNING_KEY: ecs.Secret.fromSecretsManager(sessionSigningKey),
        },
      },
    });

    // Health check hits the app's /health endpoint. Tuned to mark a new task healthy FAST:
    // 2 successes × 15s = ~30s, well inside the deployment circuit breaker's patience. The
    // defaults (5 × 30s = 150s) exceeded the grace window, so a task-def update killed a
    // perfectly healthy new task for "failed ELB health checks" before it could go healthy.
    service.targetGroup.configureHealthCheck({
      path: '/health',
      healthyHttpCodes: '200',
      interval: cdk.Duration.seconds(15),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    // The task reads HelpNeed artifacts from the ML bucket.
    props.artifactBucket.grantRead(service.taskDefinition.taskRole);

    // The task sends the COPPA parental-email verification through SES (Slice auth/parent-child).
    // Scoped to SendEmail/SendRawEmail; the verified-identity restriction is enforced SES-side
    // (the sender must be a verified identity — see AUTH.md). No static AWS creds: the task uses
    // this role. Until the SES sender identity is verified, the app falls back to logging the link.
    service.taskDefinition.taskRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['ses:SendEmail', 'ses:SendRawEmail'],
        resources: ['*'],
      }),
    );

    // ---- Frontend: private S3 bucket + CloudFront distribution.
    const siteBucket = new s3.Bucket(this, 'SiteBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      enforceSSL: true,
    });

    // Shared ALB origin reused across every API behavior. HTTP-only between CloudFront
    // and the ALB (the ALB has no cert); CloudFront terminates HTTPS for viewers.
    const albOrigin = new origins.LoadBalancerV2Origin(service.loadBalancer, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
    });

    const additionalBehaviors: Record<string, cloudfront.BehaviorOptions> = {};
    for (const pattern of API_PATH_PATTERNS) {
      additionalBehaviors[pattern] = {
        origin: albOrigin,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      };
    }

    // Custom domain + TLS for the distribution. The ACM cert (us-east-1, covers
    // whollymath.app and www) and the Route 53 alias records were created out-of-band
    // at first launch and were NOT in this stack — so a `cdk deploy` reset the
    // distribution to its code-defined state and stripped the aliases/cert, breaking
    // the custom domain (default *.cloudfront.net cert can't serve whollymath.app).
    // Declaring them here makes the binding survive every future deploy.
    // Ref: project_aws_deployment (cert arn ...995e5838, Route 53 zone Z04875931OEN82PDTA54P).
    const siteCertificate = acm.Certificate.fromCertificateArn(
      this,
      'SiteCertificate',
      'arn:aws:acm:us-east-1:463470963743:certificate/995e5838-2210-4c37-a0a4-4fcf7943f4ce',
    );

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      domainNames: ['whollymath.app', 'www.whollymath.app'],
      certificate: siteCertificate,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      defaultRootObject: 'index.html',
      additionalBehaviors,
      errorResponses: [
        {
          httpStatus: 403,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
        },
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
        },
      ],
    });

    // Deploy the built frontend into the site bucket and invalidate CloudFront.
    new s3deploy.BucketDeployment(this, 'DeploySite', {
      sources: [s3deploy.Source.asset('../frontend/dist')],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    // ---- Outputs.
    new cdk.CfnOutput(this, 'CloudFrontUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Public CloudFront URL for the WhollyMath app',
    });
    new cdk.CfnOutput(this, 'AlbDnsName', {
      value: service.loadBalancer.loadBalancerDnsName,
      description: 'Internal ALB DNS name (CloudFront origin for API paths)',
    });
    new cdk.CfnOutput(this, 'DbEndpoint', {
      value: props.dbInstance.dbInstanceEndpointAddress,
      description: 'RDS Postgres endpoint address',
    });
    new cdk.CfnOutput(this, 'AnthropicSecretArn', {
      value: anthropicSecret.secretArn,
      description: 'ARN of the Anthropic API key secret (populate the value post-deploy)',
    });
    new cdk.CfnOutput(this, 'LangsmithSecretArn', {
      value: langsmithSecret.secretArn,
      description: 'ARN of the LangSmith API key secret (populate the value post-deploy)',
    });
    new cdk.CfnOutput(this, 'MathpixSecretArn', {
      value: mathpixSecret.secretArn,
      description: 'ARN of the Mathpix app key secret (populate the value post-deploy)',
    });
  }
}
