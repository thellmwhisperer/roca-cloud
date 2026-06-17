#!/usr/bin/env python3
import aws_cdk as cdk

from roca_cloud_stack import RocaCloudStack


app = cdk.App()
RocaCloudStack(
    app,
    "RocaCloudStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-2",
    ),
)
app.synth()
