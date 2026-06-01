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
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
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

    // ---- Anthropic API key secret (real value populated post-deploy by the operator).
    const anthropicSecret = new secretsmanager.Secret(this, 'AnthropicApiKey', {
      secretName: 'whollymath/anthropic-api-key',
      description: 'Anthropic API key; populate after deploy',
      secretStringValue: cdk.SecretValue.unsafePlainText('REPLACE_ME'),
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
        },
        secrets: {
          DB_HOST: ecs.Secret.fromSecretsManager(props.dbSecret, 'host'),
          DB_USER: ecs.Secret.fromSecretsManager(props.dbSecret, 'username'),
          DB_PASSWORD: ecs.Secret.fromSecretsManager(props.dbSecret, 'password'),
          ANTHROPIC_API_KEY: ecs.Secret.fromSecretsManager(anthropicSecret),
        },
      },
    });

    // Health check hits the app's /health endpoint.
    service.targetGroup.configureHealthCheck({
      path: '/health',
      healthyHttpCodes: '200',
    });

    // The task reads HelpNeed artifacts from the ML bucket.
    props.artifactBucket.grantRead(service.taskDefinition.taskRole);

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

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
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
  }
}
