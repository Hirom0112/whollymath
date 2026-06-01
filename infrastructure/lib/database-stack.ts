// DatabaseStack — the RDS Postgres instance for WhollyMath.
//
// Budget-driven sizing (CLAUDE.md §10, $50/mo cap): t4g.micro (Graviton, cheapest
// burstable class), 20 GB gp3, single-AZ, 1-day backups. The instance lives in a
// PRIVATE_ISOLATED subnet — no public IP, no internet route — and only accepts
// connections from the shared app security group created in NetworkStack.
//
// Credentials are a Secrets Manager generated secret. We exclude URL/shell-special
// characters from the generated password so DB_PASSWORD can be safely injected as an
// env var and embedded in a connection URL by the backend without escaping surprises.
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export interface DatabaseStackProps extends cdk.StackProps {
  readonly vpc: ec2.Vpc;
  readonly appSecurityGroup: ec2.SecurityGroup;
}

export class DatabaseStack extends cdk.Stack {
  public readonly instance: rds.DatabaseInstance;
  public readonly secret: secretsmanager.ISecret;

  constructor(scope: Construct, id: string, props: DatabaseStackProps) {
    super(scope, id, props);

    this.instance = new rds.DatabaseInstance(this, 'Postgres', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.BURSTABLE4_GRAVITON,
        ec2.InstanceSize.MICRO,
      ),
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      allocatedStorage: 20,
      storageType: rds.StorageType.GP3,
      multiAz: false,
      publiclyAccessible: false,
      databaseName: 'whollymath',
      credentials: rds.Credentials.fromGeneratedSecret('whollymath', {
        // Exclude URL/shell-problematic chars so DB_PASSWORD is safe in env + connection URLs.
        excludeCharacters: '/@" \\\'%`+;()$&,:?#[]{}',
      }),
      backupRetention: cdk.Duration.days(1),
      deleteAutomatedBackups: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // The generated secret is always present for fromGeneratedSecret credentials.
    if (!this.instance.secret) {
      throw new Error('Expected RDS instance to have a generated credentials secret');
    }
    this.secret = this.instance.secret;

    // Allow the shared app SG to reach Postgres on its default port.
    this.instance.connections.allowDefaultPortFrom(
      props.appSecurityGroup,
      'Fargate tasks to Postgres',
    );
  }
}
