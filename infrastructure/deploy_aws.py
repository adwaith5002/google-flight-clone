"""Deploy the Flight Monitor stack to the AWS account configured in the CLI."""

import getpass
import os
import sys
import uuid
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-1"
STACK_NAME = "FlightMonitorDeploy"
TEMPLATE_PATH = ROOT / "infrastructure" / "aws_stack.yaml"
BUILD_DIR = ROOT / "build" / "aws"
APP_FILES = (
    "requirements.txt",
    "src/frontend/app.py",
    "src/api_fetcher/fetcher.py",
    "src/processor/alert_engine.py",
    "src/database/local_store.py",
    "src/scheduler.py",
)
LAMBDA_FILES = (
    "src/api_fetcher/fetcher.py",
    "src/processor/alert_engine.py",
    "src/database/local_store.py",
    "src/scheduler.py",
)


def check_prerequisites():
    session = boto3.Session(region_name=REGION)
    account_id = session.client("sts").get_caller_identity()["Account"]
    dynamodb = session.client("dynamodb")
    for table_name in ("TrackedRoutes", "PriceHistory", "Users"):
        response = dynamodb.describe_table(TableName=table_name)
        if response["Table"]["TableStatus"] != "ACTIVE":
            raise RuntimeError(f"DynamoDB table {table_name} is not ACTIVE")

    sns = session.client("sns")
    topic_arn = None
    for page in sns.get_paginator("list_topics").paginate():
        topic_arn = next(
            (
                topic["TopicArn"] for topic in page.get("Topics", [])
                if topic["TopicArn"].rsplit(":", 1)[-1] == "FlightPriceAlertsTopic"
            ),
            None,
        )
        if topic_arn:
            break
    if not topic_arn:
        raise RuntimeError("FlightPriceAlertsTopic was not found in us-east-1")

    ec2 = session.client("ec2")
    prefix_lists = ec2.describe_managed_prefix_lists(
        Filters=[{
            "Name": "prefix-list-name",
            "Values": ["com.amazonaws.global.cloudfront.origin-facing"],
        }]
    )["PrefixLists"]
    if not prefix_lists:
        raise RuntimeError("The CloudFront origin-facing prefix list was not found")

    cloudformation = session.client("cloudformation")
    cloudformation.validate_template(TemplateBody=TEMPLATE_PATH.read_text(encoding="utf-8"))
    try:
        cloudformation.describe_stacks(StackName=STACK_NAME)
    except ClientError as error:
        if error.response["Error"]["Code"] != "ValidationError":
            raise
    else:
        raise RuntimeError(
            f"Stack {STACK_NAME} already exists. Inspect it before updating; "
            "this deployment script intentionally does not replace existing resources."
        )

    return session, account_id, topic_arn, prefix_lists[0]["PrefixListId"]


def create_bundle(output_path, files):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative_path in files:
            source_path = ROOT / relative_path
            archive.write(source_path, relative_path.replace(os.sep, "/"))
    return output_path


def create_deployment_bucket(s3_client, account_id):
    bucket_name = f"flight-monitor-deploy-{account_id}-{uuid.uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=bucket_name)
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3_client.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    return bucket_name


def deploy():
    try:
        session, account_id, topic_arn, prefix_list_id = check_prerequisites()
    except ClientError as error:
        aws_error = error.response.get("Error", {})
        print(
            "Deployment preflight failed before creating AWS resources: "
            f"{aws_error.get('Code')}: {aws_error.get('Message')}",
            file=sys.stderr,
        )
        print(
            "Use an AWS identity permitted to inspect the existing DynamoDB/SNS "
            "resources, create CloudFormation/EC2/CloudFront/Lambda/EventBridge/S3/"
            "Secrets Manager resources, and create/pass IAM roles.",
            file=sys.stderr,
        )
        return 1

    password = getpass.getpass("Choose an app login password (minimum 16 characters): ")
    confirmation = getpass.getpass("Confirm app login password: ")
    if len(password) < 16 or password != confirmation:
        print("Passwords must match and contain at least 16 characters.", file=sys.stderr)
        return 1

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    app_bundle = create_bundle(BUILD_DIR / "app.zip", APP_FILES)
    lambda_bundle = create_bundle(BUILD_DIR / "worker.zip", LAMBDA_FILES)
    bucket_name = None
    secret_arn = None

    try:
        s3 = session.client("s3")
        bucket_name = create_deployment_bucket(s3, account_id)
        app_key = "bundles/app.zip"
        lambda_key = "bundles/worker.zip"
        s3.upload_file(str(app_bundle), bucket_name, app_key)
        s3.upload_file(str(lambda_bundle), bucket_name, lambda_key)

        secret = session.client("secretsmanager").create_secret(
            Name=f"FlightMonitorAppPassword-{uuid.uuid4().hex[:8]}",
            Description="Login password for the Flight Monitor web application",
            SecretString=password,
        )
        secret_arn = secret["ARN"]

        cloudformation = session.client("cloudformation")
        cloudformation.create_stack(
            StackName=STACK_NAME,
            TemplateBody=TEMPLATE_PATH.read_text(encoding="utf-8"),
            Parameters=[
                {"ParameterKey": "AppBundleBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "AppBundleKey", "ParameterValue": app_key},
                {"ParameterKey": "LambdaBundleBucket", "ParameterValue": bucket_name},
                {"ParameterKey": "LambdaBundleKey", "ParameterValue": lambda_key},
                {"ParameterKey": "AppPasswordSecretArn", "ParameterValue": secret_arn},
                {"ParameterKey": "NotificationTopicArn", "ParameterValue": topic_arn},
                {"ParameterKey": "CloudFrontOriginPrefixListId", "ParameterValue": prefix_list_id},
            ],
            Capabilities=["CAPABILITY_IAM"],
            Tags=[{"Key": "Project", "Value": "GoogleFlightClone"}],
        )
        print("AWS stack creation started. Waiting for resources and CloudFront...")
        cloudformation.get_waiter("stack_create_complete").wait(
            StackName=STACK_NAME,
            WaiterConfig={"Delay": 20, "MaxAttempts": 90},
        )
        stack = cloudformation.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
        outputs = {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}
        print(f"Deployment complete. App URL: {outputs['AppUrl']}")
        print(f"Scheduled worker: {outputs['ScheduledWorkerName']} (every hour)")
        print("Sign in using the password you entered above.")
        print("New tracker email addresses must confirm the SNS subscription before alerts arrive.")
        return 0
    except Exception:
        print("Deployment failed. Check CloudFormation events for the failing resource.")
        if bucket_name:
            print(f"Deployment artifacts remain in S3 bucket {bucket_name}.")
        if secret_arn:
            print("The app password secret was created in Secrets Manager and was not printed.")
        raise


if __name__ == "__main__":
    raise SystemExit(deploy())
