import datetime

from src.api_fetcher.fetcher import lambda_handler as fetch_prices
from src.processor.alert_engine import lambda_handler as evaluate_alerts


def lambda_handler(event, context):
    fetch_result = fetch_prices(event, context)
    alerts_result = evaluate_alerts(event, context)
    return {
        "statusCode": 200,
        "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "price_ingestion": fetch_result,
        "alert_evaluation": alerts_result,
    }
