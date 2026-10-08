import os
import sys
import json
import time
import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
USER_EMAIL = os.environ.get("USER_EMAIL", "adwaitharun2005@gmail.com")

print(f"=== AWS Infrastructure Auto-Provisioning Script (Region: {AWS_REGION}) ===")

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
dynamodb_client = boto3.client("dynamodb", region_name=AWS_REGION)
sns_client = boto3.client("sns", region_name=AWS_REGION)

# 1. Create DynamoDB Tables
def create_dynamodb_tables():
    tables_to_create = [
        {
            "TableName": "TrackedRoutes",
            "KeySchema": [{"AttributeName": "RouteId", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "RouteId", "AttributeType": "S"}]
        },
        {
            "TableName": "PriceHistory",
            "KeySchema": [
                {"AttributeName": "RouteId", "KeyType": "HASH"},
                {"AttributeName": "Timestamp", "KeyType": "RANGE"}
            ],
            "AttributeDefinitions": [
                {"AttributeName": "RouteId", "AttributeType": "S"},
                {"AttributeName": "Timestamp", "AttributeType": "S"}
            ]
        },
        {
            "TableName": "Users",
            "KeySchema": [{"AttributeName": "UserId", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "UserId", "AttributeType": "S"}]
        }
    ]

    for t in tables_to_create:
        t_name = t["TableName"]
        try:
            print(f"Creating DynamoDB table: {t_name}...")
            table = dynamodb.create_table(
                TableName=t_name,
                KeySchema=t["KeySchema"],
                AttributeDefinitions=t["AttributeDefinitions"],
                BillingMode="PAY_PER_REQUEST"
            )
            print(f"✅ Created {t_name}. Waiting for table to become ACTIVE...")
            table.meta.client.get_waiter("table_exists").wait(TableName=t_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                print(f"ℹ️ DynamoDB Table '{t_name}' already exists.")
            else:
                print(f"❌ Error creating table '{t_name}': {e}")

# 2. Create Amazon SNS Topic & Email Subscription
def setup_sns_notifications():
    topic_name = "FlightPriceAlertsTopic"
    try:
        print(f"Creating SNS Topic: {topic_name}...")
        res = sns_client.create_topic(Name=topic_name)
        topic_arn = res.get("TopicArn")
        print(f"✅ SNS Topic Created ARN: {topic_arn}")

        print(f"Subscribing email {USER_EMAIL} to SNS topic...")
        sub_res = sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol="email",
            Endpoint=USER_EMAIL
        )
        print(f"✅ Subscription initiated! Subscription ARN: {sub_res.get('SubscriptionArn')}")
        print(f"📩 Please check inbox '{USER_EMAIL}' and click 'Confirm Subscription'.")
        return topic_arn
    except ClientError as e:
        print(f"❌ Error setting up SNS Topic: {e}")
        return None

if __name__ == "__main__":
    try:
        # Verify AWS Credentials first
        sts = boto3.client("sts", region_name=AWS_REGION)
        identity = sts.get_caller_identity()
        print(f"AWS Credentials Validated! Connected Account ID: {identity['Account']}")
        
        create_dynamodb_tables()
        topic_arn = setup_sns_notifications()
        
        print("\n=== Setup Summary ===")
        print("1. DynamoDB Tables: TrackedRoutes, PriceHistory, Users (Active)")
        if topic_arn:
            print(f"2. SNS Topic ARN: {topic_arn}")
            print(f"   (Set $env:SNS_TOPIC_ARN='{topic_arn}')")
        print("\nDeployment setup completed successfully!")

    except ClientError as e:
        print(f"\n❌ AWS Authentication Error: {e}")
        print("Please run 'aws configure' or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
