// MlStack — the S3 bucket holding ML artifacts (HelpNeed predictor re-fits).
//
// The HelpNeed predictor is re-trained offline and its artifacts (the XGBoost model
// plus the trustworthy_kcs stamp the Tier-2 guard reads) land here; the Fargate task
// is granted read access in AppStack. Encrypted, private, SSL-only.
import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class MlStack extends cdk.Stack {
  public readonly artifactBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.artifactBucket = new s3.Bucket(this, 'ArtifactBucket', {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
    });
  }
}
