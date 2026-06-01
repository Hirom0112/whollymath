// NetworkStack — the VPC and the shared application security group.
//
// Budget-driven design (CLAUDE.md §10 cost controls, $50/mo cap): natGateways:0.
// NAT gateways are ~$32/mo each and would blow the budget on their own. Instead,
// the Fargate tasks run in PUBLIC subnets with a public IP (see AppStack) so they
// reach ECR + the Anthropic API through the Internet Gateway, and Postgres lives
// in a PRIVATE_ISOLATED subnet with no internet route at all.
//
// The application security group is created here (not in AppStack) so DatabaseStack
// can grant it Postgres ingress without a circular stack dependency: Database depends
// on Network, App depends on both — but Network depends on neither.
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export class NetworkStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly appSecurityGroup: ec2.SecurityGroup;
  public readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // Shared SG that carries the cross-stack grants: DatabaseStack grants this SG
    // Postgres ingress, and AppStack attaches it to the Fargate tasks (in addition to
    // the task's own generated SG). Keeping it here, in the stack that depends on
    // nothing, is what lets DatabaseStack reference it without a dependency cycle.
    this.appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      vpc: this.vpc,
      description: 'Shared SG for WhollyMath Fargate tasks (egress to ECR/Anthropic, ingress to RDS granted in DatabaseStack)',
      allowAllOutbound: true,
    });

    // The public ALB's security group, owned here in NetworkStack alongside the task SG.
    // Co-locating both SGs lets us author the ALB->task ingress rule intra-stack (below),
    // which is what keeps AppStack -> NetworkStack the only edge between them. If instead
    // the ecs_patterns construct generated the ALB SG in AppStack, its auto-added ingress
    // rule would live on the NetworkStack task SG but reference the AppStack ALB SG,
    // reversing the edge and creating a cross-stack dependency cycle.
    this.albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc: this.vpc,
      description: 'WhollyMath public ALB SG (HTTP 80 from the internet; CloudFront is the real client)',
      allowAllOutbound: true,
    });
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Public HTTP to ALB (fronted by CloudFront)',
    );

    // ALB -> Fargate container port, authored here so the rule is intra-NetworkStack.
    this.appSecurityGroup.addIngressRule(
      this.albSecurityGroup,
      ec2.Port.tcp(8000),
      'ALB to Fargate container port',
    );
  }
}
