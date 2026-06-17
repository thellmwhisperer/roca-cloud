from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_budgets as budgets,
    aws_certificatemanager as acm,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class RocaCloudStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        root = Path(__file__).resolve().parents[1]

        vpc = ec2.Vpc(
            self,
            "RocaVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        lambda_sg = ec2.SecurityGroup(
            self,
            "RocaLambdaSecurityGroup",
            vpc=vpc,
            description="Roca Cloud Lambda egress to private Postgres",
            allow_all_outbound=True,
        )
        db_sg = ec2.SecurityGroup(
            self,
            "RocaDbSecurityGroup",
            vpc=vpc,
            description="Private RDS PostgreSQL reachable only from Roca Lambda",
            allow_all_outbound=False,
        )
        db_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Lambda to Postgres")

        endpoint_sg = ec2.SecurityGroup(
            self,
            "RocaEndpointSecurityGroup",
            vpc=vpc,
            description="Interface endpoints reachable from Roca Lambda",
            allow_all_outbound=True,
        )
        endpoint_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(443), "Lambda to VPC endpoints")
        vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[endpoint_sg],
        )

        database = rds.DatabaseInstance(
            self,
            "RocaPostgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_13
            ),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[db_sg],
            database_name="roca",
            credentials=rds.Credentials.from_generated_secret("roca"),
            allocated_storage=20,
            max_allocated_storage=20,
            multi_az=False,
            publicly_accessible=False,
            deletion_protection=False,
            delete_automated_backups=True,
            backup_retention=Duration.days(1),
            removal_policy=RemovalPolicy.DESTROY,
        )

        api_token_secret = secretsmanager.Secret(
            self,
            "RocaApiTokenSecret",
            secret_name=self.node.try_get_context("apiTokenSecretName") or "roca-cloud/api-tokens",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template="{}",
                generate_string_key="edu",
                exclude_punctuation=True,
                password_length=40,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        fn = lambda_.DockerImageFunction(
            self,
            "RocaApiFunction",
            code=lambda_.DockerImageCode.from_image_asset(str(root)),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=512,
            timeout=Duration.seconds(30),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[lambda_sg],
            log_retention=logs.RetentionDays.THREE_DAYS,
            environment={
                "DB_HOST": database.db_instance_endpoint_address,
                "DB_PORT": database.db_instance_endpoint_port,
                "DB_NAME": "roca",
                "DB_SECRET_ARN": database.secret.secret_arn,
                "ROCA_AUTH_TOKEN_SECRET_ARN": api_token_secret.secret_arn,
            },
        )
        database.secret.grant_read(fn)
        api_token_secret.grant_read(fn)

        integration = apigw_integrations.HttpLambdaIntegration("RocaApiIntegration", fn)
        api = apigwv2.HttpApi(
            self,
            "RocaHttpApi",
            api_name="roca-cloud",
            default_integration=integration,
        )

        custom_domain_name = self.node.try_get_context("customDomainName")
        certificate_arn = self.node.try_get_context("certificateArn")
        if bool(custom_domain_name) != bool(certificate_arn):
            raise ValueError("customDomainName and certificateArn must be provided together")
        if custom_domain_name:
            certificate = acm.Certificate.from_certificate_arn(
                self,
                "RocaCustomDomainCertificate",
                certificate_arn,
            )
            domain_name = apigwv2.DomainName(
                self,
                "RocaCustomDomain",
                domain_name=custom_domain_name,
                certificate=certificate,
            )
            apigwv2.ApiMapping(
                self,
                "RocaCustomDomainMapping",
                api=api,
                domain_name=domain_name,
            )
            CfnOutput(self, "RocaCustomDomainUrl", value=f"https://{custom_domain_name}")
            CfnOutput(self, "RocaCloudflareCnameTarget", value=domain_name.regional_domain_name)

        budget_email = self.node.try_get_context("budgetEmail")
        if budget_email:
            budgets.CfnBudget(
                self,
                "RocaDemoBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="roca-cloud-demo-budget",
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(
                        amount=100,
                        unit="USD",
                    ),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            comparison_operator="GREATER_THAN",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                            notification_type="ACTUAL",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL",
                                address=budget_email,
                            )
                        ],
                    )
                ],
            )

        CfnOutput(self, "RocaApiUrl", value=api.api_endpoint)
        CfnOutput(self, "RocaDbEndpoint", value=database.db_instance_endpoint_address)
        CfnOutput(self, "RocaApiTokenSecretArn", value=api_token_secret.secret_arn)
