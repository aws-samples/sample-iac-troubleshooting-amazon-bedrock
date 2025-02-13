# Accelerate IaC Troubleshooting with Agents for Amazon Bedrock

This repository contains two AWS Lambda functions designed to automate and streamline the troubleshooting of Infrastructure as Code (IaC) issues, specifically for Terraform. These Lambdas are deployed and invoked via **Amazon Bedrock Agents** using action groups to provide **context-aware troubleshooting** guidance and direct developers to appropriate teams when needed.

## Overview

### 1. **`terraform-troubleshooting.py`**
This Lambda function acts as the orchestrator for troubleshooting Terraform issues. It receives the error context from Amazon Bedrock Agents and forwards relevant details to the second Lambda. Once it collects the necessary error logs and repository data, it generates prompts for Amazon Bedrock's model to provide troubleshooting steps.

### 2. **`fetch-error-code-details.py`**
This Lambda function is invoked by the first Lambda (`terraform-troubleshooting.py`) and is responsible for retrieving error logs from Terraform Cloud workspaces and fetching relevant Terraform files from the GitLab repository. It then returns the data for further analysis.

## Architecture Flow

1. The **Bedrock Agent** receives a request from the user to troubleshoot a Terraform error.
2. **Action groups** within the Bedrock Agent trigger `terraform-troubleshooting.py`.
3. `terraform-troubleshooting.py` invokes `fetch-error-code-details.py` to gather error logs from Terraform Cloud and retrieve the relevant Terraform files from GitLab.
4. `fetch-error-code-details.py` returns the error message and repository data.
5. `terraform-troubleshooting.py` constructs a prompt based on the error and repository content and sends it to the Bedrock model for analysis.
6. The Bedrock model returns context-aware troubleshooting steps.
7. The Bedrock Agent provides the troubleshooting steps to the user or directs them to the appropriate teams if necessary.

## Setup

### Prerequisites

- AWS Lambda functions (deployed via Bedrock Agent)
- Amazon Bedrock Agent with configured action groups
- Terraform Cloud API token
- GitLab API token
- Python 3.8 or higher

### Environment Variables

#### **`terraform-troubleshooting.py`**
- `LAMBDA_2_FUNCTION_NAME`: The name of the Lambda function (`fetch-error-code-details.py`) to invoke for fetching error and repo details.
- `BEDROCK_MODEL_ID`: The Bedrock model used to analyze errors and generate troubleshooting steps (e.g., `anthropic.claude-3-sonnet-20240229-v1:0`).

#### **`fetch-error-code-details.py`**
- `TERRAFORM_SECRET_NAME`: The name of the secret containing the Terraform Cloud API token, stored in AWS Secrets Manager.
- `VCS_SECRET_NAME`: The name of the secret containing the GitLab API token, stored in AWS Secrets Manager.
- `TERRAFORM_API_URL`: The base API URL for Terraform Cloud.

## Deployment

The Lambda functions are deployed as part of an **Amazon Bedrock Agent** setup, and the agent uses **action groups** to invoke them. Here's how to set up the deployment:

1. **Clone the repository**:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2. **Install dependencies**:
    Both Lambda functions use the Python `requests` package. Ensure it's included in your deployment package or Lambda Layer.
    ```bash
    pip install requests -t ./package
    ```

3. **Package and deploy the Lambda functions**:
    Package the Lambda functions with their dependencies and upload them to AWS Lambda.

4. **Configure environment variables**:
    Set the required environment variables (`LAMBDA_2_FUNCTION_NAME`, `TERRAFORM_SECRET_NAME`, etc.) in the AWS Lambda console for each function.

5. **Amazon Bedrock Agent configuration**:
    - Ensure the **Bedrock Agent** is set up with **action groups** that map to the `terraform-troubleshooting.py` Lambda function.
    - Define the correct input parameters (such as workspace URL, repo URL, branch name) that the action group will forward to the Lambda functions.

## Example Workflow

### Step 1: User Submission
The user submits a request to troubleshoot a Terraform error via the Bedrock Agent interface, providing details such as the Terraform Cloud workspace URL and GitLab repository URL.

### Step 2: Action Group Invocation
The Bedrock Agent triggers the `terraform-troubleshooting.py` Lambda via its action group, forwarding the error details.

### Step 3: Fetching Error Details
`terraform-troubleshooting.py` invokes `fetch-error-code-details.py` to gather the error log from Terraform Cloud and retrieve relevant Terraform files from GitLab.

### Step 4: Prompt Construction and Troubleshooting
`terraform-troubleshooting.py` constructs a prompt with the error and code context and sends it to the Bedrock model. The Bedrock model returns context-aware troubleshooting steps, which are provided to the user via the Bedrock Agent.

## Testing

You can test the Lambda functions locally or through the AWS Lambda console. Ensure that your Bedrock Agent action groups are correctly set up to pass the necessary parameters to the Lambda functions.

### Sample Input (from Bedrock Agent):
```json
{
    "agent": "terraform_troubleshooter",
    "actionGroup": "IaC troubleshooting",
    "function": "troubleshoot_error",
    "parameters": [
        {"name": "workspace_url", "value": "https://app.terraform.io/app/org/workspaces/workspace_name"},
        {"name": "repo_url", "value": "https://gitlab.com/example/repo"},
        {"name": "branch_name", "value": "main"}
    ]
}
```

### Expected Output:
The Bedrock Agent will return context-aware troubleshooting steps or escalate the issue to relevant teams based on platform guardrails.

## Security

Ensure that API tokens for Terraform Cloud and GitLab are stored securely in AWS Secrets Manager. Follow the least privilege principle when assigning IAM roles to the Lambda functions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.