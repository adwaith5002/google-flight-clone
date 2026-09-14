# Cloud-Based Flight Price Monitoring System

A serverless, event-driven application built on AWS to track flight prices and alert users when fares drop below their target threshold.

## Architecture Stack

- **Compute:** AWS Lambda, Amazon EventBridge
- **Database:** Amazon DynamoDB
- **Messaging and notifications:** Amazon SNS and Amazon SQS
- **API integration:** Amadeus Self-Service API
- **Frontend:** Streamlit, Flask, or React

## Project Structure

```text
.github/workflows/  CI/CD workflows
src/api_fetcher/    Amadeus API integration and Lambda ingestion handlers
src/database/       DynamoDB helpers, schemas, and data access
src/processor/      Price comparison and alert processing
src/frontend/       User interface and API Gateway handlers
infrastructure/     Terraform or CloudFormation templates
```

## Team Responsibilities

- **Member A (API and Ingestion):** Lambda functions and Amadeus API integration.
- **Member B (Database):** DynamoDB schema design and data models.
- **Member C (Processing and Alerts):** Price comparison logic and SNS notifications.
- **Member D (Frontend and Integration):** User interface and API Gateway setup.

## Getting Started

1. Create and activate a Python virtual environment.
2. Install the pinned dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Add AWS and Amadeus credentials through environment variables or the AWS shared credentials configuration. Do not commit secrets to the repository.
4. Add implementation code to the source directory owned by your team member.

## Status

The repository currently contains the shared project scaffold. Service implementations and infrastructure definitions will be added by the team.
