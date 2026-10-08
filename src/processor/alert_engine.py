import os
import json
import datetime
import decimal
import logging
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from src.database.local_store import latest_price_record, load_items

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables & table names
TRACKED_ROUTES_TABLE = os.environ.get("TRACKED_ROUTES_TABLE", "TrackedRoutes")
PRICE_HISTORY_TABLE = os.environ.get("PRICE_HISTORY_TABLE", "PriceHistory")
USERS_TABLE = os.environ.get("USERS_TABLE", "Users")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def get_active_tracked_routes():
    """
    Data Evaluator:
    Queries/scans the TrackedRoutes DynamoDB table to retrieve all active
    flight tracking configurations and target price thresholds.
    """
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(TRACKED_ROUTES_TABLE)
        items = []
        response = table.scan()
        items.extend(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        by_id = {
            item["RouteId"]: item for item in load_items("trackers")
            if item.get("RouteId")
        }
        by_id.update({item["RouteId"]: item for item in items})
        return list(by_id.values())
    except Exception as e:
        logger.warning(f"Could not scan DynamoDB TrackedRoutes table ({e})")
        return load_items("trackers")


def get_latest_price_history(route_id):
    """
    Price History Retriever:
    Queries the PriceHistory DynamoDB table for a given RouteId to retrieve
    the most recent price observation (ordered by Timestamp descending).
    """
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(PRICE_HISTORY_TABLE)
        response = table.query(
            KeyConditionExpression=Key("RouteId").eq(str(route_id)),
            ScanIndexForward=False,  # Sort descending by Timestamp
            Limit=1
        )
        items = response.get("Items", [])
        if items:
            latest = items[0]
            dynamodb_latest = {
                "RouteId": latest.get("RouteId"),
                "Price": float(latest.get("Price", 0)),
                "Airline": latest.get("Airline", "Unknown Airline"),
                "Timestamp": latest.get("Timestamp", "")
            }
            local_latest = latest_price_record(route_id)
            if local_latest and local_latest.get("Timestamp", "") > dynamodb_latest["Timestamp"]:
                return local_latest
            return dynamodb_latest
    except Exception as e:
        logger.warning(f"Could not query PriceHistory for route {route_id} ({e})")

    local_latest = latest_price_record(route_id)
    if local_latest:
        return {
            **local_latest,
            "Price": float(local_latest["Price"]),
        }
    return {
        "RouteId": str(route_id),
        "Price": 0.0,
        "Airline": "Unknown Airline",
        "Timestamp": ""
    }


def get_user_email(user_id):
    """
    User Lookup:
    Queries the Users DynamoDB table to retrieve user notification email address.
    If user_id is already an email format, returns directly. Returns None when
    no address is configured instead of sending alerts to an unrelated default.
    """
    if isinstance(user_id, str) and "@" in user_id:
        return user_id
    
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(USERS_TABLE)
        response = table.get_item(Key={"UserId": str(user_id)})
        item = response.get("Item")
        if item and "Email" in item:
            return item["Email"]
    except Exception as e:
        logger.warning(f"User lookup failed for UserId {user_id} ({e})")
    
    logger.warning(f"No notification email found for UserId {user_id}")
    return None


def send_sns_price_alert(user_email, route_info, latest_price_info):
    """
    Publishes a price alert through an email-filtered SNS topic subscription.
    """
    if not user_email:
        logger.error("No recipient email configured; no email was sent")
        return False, "Recipient email is not configured"

    route_id = route_info.get("RouteId", "N/A")
    origin = route_info.get("Origin", route_info.get("origin", "N/A"))
    dest = route_info.get("Destination", route_info.get("destination", "N/A"))
    target_price = float(route_info.get("TargetPrice", route_info.get("target_price", 0)))
    curr_price = float(latest_price_info.get("Price", 0))
    airline = latest_price_info.get("Airline", "Airline")
    dep_date = route_info.get("DepartureDate", route_info.get("departure_date", "N/A"))
    
    subject = f"✈️ Price Drop Alert! {origin} ➔ {dest} is now ₹{curr_price:,.2f}"
    message = (
        f"Great news! The price for your tracked flight route has dropped below your target price threshold.\n\n"
        f"Route Details:\n"
        f"• Route: {origin} to {dest}\n"
        f"• Departure Date: {dep_date}\n"
        f"• Airline: {airline}\n"
        f"• Current Price: ₹{curr_price:,.2f}\n"
        f"• Your Target Price: ₹{target_price:,.2f}\n"
        f"• Savings: ₹{(target_price - curr_price):,.2f}\n\n"
        f"Recipient Email: {user_email}\n"
        f"Route ID: {route_id}\n"
        f"Timestamp: {latest_price_info.get('Timestamp', '')}\n\n"
        f"— Cloud Flight Price Monitoring System"
    )
    
    topic_arn = os.environ.get("SNS_TOPIC_ARN", SNS_TOPIC_ARN)
    if topic_arn:
        try:
            sns_client = boto3.client("sns", region_name=AWS_REGION)
            paginator = sns_client.get_paginator("list_subscriptions_by_topic")
            subscriptions = [
                sub for page in paginator.paginate(TopicArn=topic_arn)
                for sub in page.get("Subscriptions", [])
                if sub.get("Protocol") == "email"
            ]
            subscription = next((
                sub for sub in subscriptions
                if sub.get("Endpoint", "").lower() == user_email.lower()
            ), None)
            if not subscription:
                sns_client.subscribe(
                    TopicArn=topic_arn,
                    Protocol="email",
                    Endpoint=user_email,
                )
                logger.info(f"Requested SNS email subscription confirmation for {user_email}")
                return False, "EMAIL_CONFIRMATION_REQUIRED"
            if subscription.get("SubscriptionArn") == "PendingConfirmation":
                return False, "EMAIL_CONFIRMATION_REQUIRED"
            for email_subscription in subscriptions:
                subscription_arn = email_subscription.get("SubscriptionArn")
                endpoint = email_subscription.get("Endpoint", "").lower()
                if subscription_arn and subscription_arn != "PendingConfirmation" and endpoint:
                    sns_client.set_subscription_attributes(
                        SubscriptionArn=subscription_arn,
                        AttributeName="FilterPolicy",
                        AttributeValue=json.dumps({"Email": [endpoint]}),
                    )
            response = sns_client.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=message,
                MessageAttributes={
                    "Email": {
                        "DataType": "String",
                        "StringValue": user_email.lower()
                    }
                },
            )
            logger.info(f"Successfully sent SNS alert message ID {response.get('MessageId')} to {user_email}")
            return True, response.get("MessageId")
        except ClientError as e:
            logger.error(f"Failed to publish SNS message: {e}")
            return False, str(e)
    else:
        logger.error("SNS_TOPIC_ARN is not configured; no email was sent")
        return False, "SNS_TOPIC_ARN is not configured"


def evaluate_route_price_alerts():
    """
    Core Evaluation Workflow:
    1. Query active routes from TrackedRoutes table.
    2. Query latest price entry from PriceHistory table.
    3. Compare Current Price vs TargetPrice threshold.
    4. Trigger SNS alert if Price <= TargetPrice.
    """
    active_routes = get_active_tracked_routes()
    evaluation_results = []
    alerts_sent = 0
    
    for route in active_routes:
        route_id = route.get("RouteId", route.get("route_id"))
        target_price = float(route.get("TargetPrice", route.get("target_price", 0)))
        user_id = route.get("UserId", route.get("email"))
        
        # 1. Fetch latest price
        latest_price_info = get_latest_price_history(route_id)
        current_price = latest_price_info.get("Price", 0)
        
        # 2. Compare logic (Price <= TargetPrice)
        price_drop_triggered = current_price <= target_price
        alert_status = "Skipped (Price higher than target)"
        
        if price_drop_triggered:
            # 3. Lookup user & send alert
            user_email = get_user_email(user_id)
            success, alert_ref = send_sns_price_alert(user_email, route, latest_price_info)
            if success:
                alerts_sent += 1
                alert_status = "Alert accepted by SNS"
            else:
                alert_status = f"Alert not sent ({alert_ref})"
        
        evaluation_results.append({
            "RouteId": route_id,
            "Origin": route.get("Origin", route.get("origin")),
            "Destination": route.get("Destination", route.get("destination")),
            "TargetPrice": target_price,
            "CurrentPrice": current_price,
            "AlertTriggered": price_drop_triggered,
            "Status": alert_status
        })
    
    return evaluation_results, alerts_sent


def lambda_handler(event, context):
    """
    AWS Lambda Handler:
    Wraps the evaluation & alert workflow so it can run as an automated background job.
    """
    logger.info(f"Processor Lambda triggered with event: {json.dumps(event)}")
    
    results, alerts_sent = evaluate_route_price_alerts()
    
    response_payload = {
        "message": f"Processed {len(results)} active route evaluation(s). Triggered {alerts_sent} price drop alert(s).",
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alerts_triggered_count": alerts_sent,
        "evaluation_summary": results
    }
    
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(response_payload)
    }


if __name__ == "__main__":
    print("=== Testing Event-Driven Processor Alert Engine (src/processor/alert_engine.py) ===")
    test_output = lambda_handler({}, None)
    print(json.dumps(test_output, indent=2))
