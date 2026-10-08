terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "notification_email" {
  type    = string
  default = "adwaitharun2005@gmail.com"
}

# 1. DynamoDB Tables
resource "aws_dynamodb_table" "tracked_routes" {
  name         = "TrackedRoutes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "RouteId"

  attribute {
    name = "RouteId"
    type = "S"
  }

  tags = {
    Environment = "Production"
    Project     = "GoogleFlightClone"
  }
}

resource "aws_dynamodb_table" "price_history" {
  name         = "PriceHistory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "RouteId"
  range_key    = "Timestamp"

  attribute {
    name = "RouteId"
    type = "S"
  }

  attribute {
    name = "Timestamp"
    type = "S"
  }

  tags = {
    Environment = "Production"
    Project     = "GoogleFlightClone"
  }
}

resource "aws_dynamodb_table" "users" {
  name         = "Users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "UserId"

  attribute {
    name = "UserId"
    type = "S"
  }

  tags = {
    Environment = "Production"
    Project     = "GoogleFlightClone"
  }
}

# 2. Amazon SNS Topic & Email Subscription
resource "aws_sns_topic" "flight_price_alerts" {
  name = "FlightPriceAlertsTopic"
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.flight_price_alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# 3. Output Variables
output "tracked_routes_table_arn" {
  value = aws_dynamodb_table.tracked_routes.arn
}

output "price_history_table_arn" {
  value = aws_dynamodb_table.price_history.arn
}

output "sns_topic_arn" {
  value = aws_sns_topic.flight_price_alerts.arn
}
