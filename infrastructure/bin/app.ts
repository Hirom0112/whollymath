#!/usr/bin/env node
// CDK app entry point. Instantiates the four stacks and threads cross-stack props.
// One stack per logical concern (CLAUDE.md §10): Network, Database, Ml, App.
import * as cdk from 'aws-cdk-lib';
import { NetworkStack } from '../lib/network-stack';
import { DatabaseStack } from '../lib/database-stack';
import { MlStack } from '../lib/ml-stack';
import { AppStack } from '../lib/app-stack';

const app = new cdk.App();

// Pinned to the WhollyMath production account/region (CLAUDE.md §10 — single prod env).
const env: cdk.Environment = {
  account: '463470963743',
  region: 'us-east-1',
};

const network = new NetworkStack(app, 'WhollymathNetwork', { env });

const database = new DatabaseStack(app, 'WhollymathDatabase', {
  env,
  vpc: network.vpc,
  appSecurityGroup: network.appSecurityGroup,
});

const ml = new MlStack(app, 'WhollymathMl', { env });

new AppStack(app, 'WhollymathApp', {
  env,
  vpc: network.vpc,
  appSecurityGroup: network.appSecurityGroup,
  albSecurityGroup: network.albSecurityGroup,
  dbInstance: database.instance,
  dbSecret: database.secret,
  artifactBucket: ml.artifactBucket,
});

app.synth();
