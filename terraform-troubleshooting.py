import json
import logging
import os
import boto3
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Boto3 clients
bedrock = boto3.client(service_name='bedrock-runtime')
lambda_client = boto3.client('lambda')

# Environment variables
LAMBDA_2_FUNCTION_NAME = os.environ.get('LAMBDA_2_FUNCTION_NAME')

def invoke_bedrock_model(prompt):
    try:
        # Set Claude model ID directly
        model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        })

        response = bedrock.invoke_model(
            modelId=model_id,
            body=body,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        return response_body['content'][0]['text']

    except Exception as e:
        logger.error(f"Error invoking Bedrock model: {e}")
        raise

def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', {})

    try:
        properties = {param["name"]: param["value"] for param in parameters}
        workspace_url = properties.get('workspace_url')
        repo_url = properties.get('repo_url', None)
        branch_name = properties.get('branch_name', 'main')

        # Create a payload for Lambda 2
        payload = {
            "workspace_url": workspace_url,
            "repo_url": repo_url,
            "branch_name": branch_name
        }

        # Invoke Lambda 2
        response = lambda_client.invoke(
            FunctionName=LAMBDA_2_FUNCTION_NAME,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )

        # Process the response from Lambda 2
        response_payload = json.loads(response['Payload'].read())
        response_body = json.loads(response_payload['body'])

        # Ensure the response contains the necessary keys
        error_message = response_body.get('error_message')
        repo_files_content = response_body.get('files_content', '')
        specific_use_case = f"""
        - If the error is with respect to service control policies or resource based policies then inform the user to contact Security team (abc-security@abc.com) as it is a limitation. DO NOT include any other information.
        - If the error is with respect to S3 bucket creation or VPC resource creation, inform the user to contact Platform team (abc-platform@abc.com) as it is a limitation. DO NOT include any other information.
        """

        print(f'error: {error_message}')
        print(f'repo: {repo_files_content}')
        if error_message is None and repo_files_content == '':
            raise KeyError("Neither 'files_content' nor 'error_message' were found in the response from Lambda 2")

        # Construct the prompt for the Bedrock model
        prompt = f"""
        <task>
        You are an expert in troubleshooting Terraform code issues. Below is an error message and the contents of a Git repository.
        Please provide detailed troubleshooting steps to resolve the issue.

        <error_message>
        {error_message}
        </error_message>

        <repo_files_content>
        {repo_files_content}
        </repo_files_content>
        
        <instructions>
        Provide step-by-step instructions on how to resolve the error in terraform enterprise environment, taking into account the specific context provided by the repository files. Ensure that the troubleshooting steps are provided aligning to {specific_use_case}.
        </instructions>
        </task>
        """
        print(f"prompt: {prompt}")
        # Invoke Bedrock model to get troubleshooting steps
        troubleshooting_steps = invoke_bedrock_model(prompt)
        logger.info("Generated troubleshooting steps: %s", troubleshooting_steps)

        responseBody = {
            "TEXT": {
                "body": troubleshooting_steps
            }
        }

        # Prepare the action response
        action_response = {
            'actionGroup': actionGroup,
            'function': function,
            'functionResponse': {
                'responseBody': responseBody
            }
        }

        # Final response structure expected by Bedrock agent
        final_response = {'response': action_response, 'messageVersion': event['messageVersion']}
        logger.info("Response: %s", json.dumps(final_response))

        return final_response

    except KeyError as ke:
        logger.error(f"Key error: {str(ke)}")
        responseBody = {
            "TEXT": {
                "body": f"Missing required information: {str(ke)}"
            }
        }
        action_response = {
            'actionGroup': actionGroup,
            'function': function,
            'functionResponse': {
                'responseBody': responseBody
            }
        }
        final_response = {'response': action_response, 'messageVersion': event['messageVersion']}
        return final_response

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        responseBody = {
            "TEXT": {
                "body": f"Error: {str(e)}"
            }
        }
        action_response = {
            'actionGroup': actionGroup,
            'function': function,
            'functionResponse': {
                'responseBody': responseBody
            }
        }
        final_response = {'response': action_response, 'messageVersion': event['messageVersion']}
        return final_response
