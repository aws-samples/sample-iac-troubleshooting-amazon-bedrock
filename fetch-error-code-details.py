import json
import logging
import os
import shutil
import boto3
import requests
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Boto3 clients
secrets_client = boto3.client('secretsmanager')

# Environment variables
TERRAFORM_SECRET_NAME = os.environ.get('TERRAFORM_SECRET_NAME')
VCS_SECRET_NAME = os.environ.get('VCS_SECRET_NAME')

# The name of the secret in Secrets Manager
TERRAFORM_API_URL = os.environ.get('TERRAFORM_API_URL')

def get_secret(secret_name):
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
    except ClientError as error:
        logger.error(f"Error retrieving secret {secret_name}: {error}")
        raise error

    if "SecretString" in response:
        return json.loads(response["SecretString"])
    else:
        raise ValueError("Secret binary is not supported")

def get_workspace_id_from_url(workspace_url):
    parts = workspace_url.split('/')
    
    if 'runs' in parts:
        workspace_name = parts[-3]  # Workspace name is 3rd to last
        org_name = parts[-5]        # Org name is 5th to last
        run_id = parts[-1]          # Run ID is the last part
    else:
        workspace_name = parts[-1]  # Workspace name is last part
        org_name = parts[-3]        # Org name is 3rd to last
        run_id = None               # No specific run ID provided
    
    return workspace_name, org_name, run_id

def get_latest_run_error(workspace_name, org_name, tfe_api_token, run_id=None):
    logger.info(f"Fetching workspace details for workspace_name: {workspace_name}, org_name: {org_name}")

    headers = {
        'Authorization': f'Bearer {tfe_api_token}',
        'Content-Type': 'application/vnd.api+json'
    }

    if run_id:
        # Fetch details for the specific run
        logger.info(f"Fetching details for specific run_id: {run_id}")
        runs_response = requests.get(
            f"{TERRAFORM_API_URL}/runs/{run_id}",
            headers=headers,
            timeout=60
        )
        runs_response.raise_for_status()
        latest_run = runs_response.json()['data']
    else:
        try:
            # Fetch workspace details to get the workspace ID
            workspace_response = requests.get(
                f"{TERRAFORM_API_URL}/organizations/{org_name}/workspaces/{workspace_name}",
                headers=headers,
                timeout=60
            )
            workspace_response.raise_for_status()
            workspace_id = workspace_response.json()['data']['id']
            logger.info(f"Retrieved workspace ID: {workspace_id}")

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching workspace ID: {http_err}")
            raise
        except Exception as e:
            logger.error(f"Error occurred while fetching workspace ID: {e}")
            raise

        try:
            # Fetch all runs for the workspace
            logger.info(f"Fetching runs for workspace_id: {workspace_id}")
            runs_response = requests.get(
                f"{TERRAFORM_API_URL}/workspaces/{workspace_id}/runs",
                headers=headers,
                timeout=60
            )
            runs_response.raise_for_status()
            runs_data = runs_response.json()['data']
            logger.info(f"Retrieved {len(runs_data)} runs for the workspace.")

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching runs: {http_err}")
            raise
        except Exception as e:
            logger.error(f"Error occurred while fetching runs: {e}")
            raise

        if not runs_data:
            logger.warning("No runs found for the workspace.")
            return "No runs found for the workspace."

        # Check only the most recent run
        latest_run = runs_data[0]
    
    run_status = latest_run['attributes']['status']
    run_id = latest_run['id']
    logger.info(f"Checking run_id: {run_id} with status: {run_status}")

    if run_status == 'errored':
        try:
            # Check for plan errors first
            if 'plan' in latest_run['relationships']:
                plan_id = latest_run['relationships']['plan']['data']['id']
                logger.info(f"Fetching plan details for plan_id: {plan_id}")
                plan_response = requests.get(
                    f"{TERRAFORM_API_URL}/plans/{plan_id}",
                    headers=headers,
                    timeout=60
                )
                plan_response.raise_for_status()

                plan_details = plan_response.json()
                log_read_url = plan_details.get('data', {}).get('attributes', {}).get('log-read-url')
                
                if log_read_url:
                    logger.info(f"Fetching logs from plan log-read-url: {log_read_url}")
                    log_response = requests.get(log_read_url, timeout=60)
                    log_response.raise_for_status()

                    log_content = log_response.text
                    error_lines = extract_error_with_context(log_content)
                    if error_lines:
                        logger.error(f"Plan Error Lines:\n{error_lines}")  # Print out the error lines
                        return f"Plan Error:\n{error_lines}"

            # If no plan errors, check for apply errors
            if 'apply' in latest_run['relationships']:
                apply_id = latest_run['relationships']['apply']['data']['id']
                logger.info(f"Fetching apply details for apply_id: {apply_id}")
                apply_response = requests.get(
                    f"{TERRAFORM_API_URL}/applies/{apply_id}",
                    headers=headers,
                    timeout=60
                )
                apply_response.raise_for_status()

                apply_details = apply_response.json()
                log_read_url = apply_details.get('data', {}).get('attributes', {}).get('log-read-url')
                
                if log_read_url:
                    logger.info(f"Fetching logs from apply log-read-url: {log_read_url}")
                    log_response = requests.get(log_read_url, timeout=60)
                    log_response.raise_for_status()

                    log_content = log_response.text
                    error_lines = extract_error_with_context(log_content)
                    if error_lines:
                        logger.error(f"Apply Error Lines:\n{error_lines}")  # Print out the error lines
                        return f"Apply Error:\n{error_lines}"

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred while fetching plan/apply details or logs: {http_err}")
        except Exception as e:
            logger.error(f"Error occurred while fetching plan/apply details or logs: {e}")

    logger.warning("No errors found in the latest run's plan or apply output.")
    return "No errors found in the latest run's plan or apply output."

def extract_error_with_context(log_content, context_lines=5):
    """
    Extract error lines and include a few lines of context after each error.
    """
    log_lines = log_content.splitlines()
    error_lines_with_context = []
    
    for i, line in enumerate(log_lines):
        if any(keyword in line.lower() for keyword in ['"@level":"error"', 'error:']):
            # Capture context lines after the error line
            end_index = min(i + context_lines + 1, len(log_lines))
            error_context = log_lines[i:end_index]
            error_lines_with_context.extend(error_context)
            error_lines_with_context.append("")  # Add a blank line for separation

    return "\n".join(error_lines_with_context)

def fetch_files_from_gitlab(repo_url, branch_name, gitlab_token):
    # Fetch repository contents using the GitLab API
    repo_path = repo_url.split("https://gitlab.com/")[-1].rstrip('/')
    api_endpoint = f"https://gitlab.com/api/v4/projects/{requests.utils.quote(repo_path, safe='')}/repository/tree?ref={branch_name}&recursive=true"
    
    headers = {
        "Authorization": f"Bearer {gitlab_token}"
    }

    response = requests.get(api_endpoint, headers=headers, timeout=60)
    response.raise_for_status()
    
    files_content = ""
    terraform_extensions = ['.tf', '.tfvars']
    
    for item in response.json():
        if item['type'] == 'blob' and any(item['path'].endswith(ext) for ext in terraform_extensions):
            file_response = requests.get(f"https://gitlab.com/api/v4/projects/{requests.utils.quote(repo_path, safe='')}/repository/files/{requests.utils.quote(item['path'], safe='')}/raw?ref={branch_name}", headers=headers, timeout=60)
            file_response.raise_for_status()
            files_content += f"File: {item['path']}\n"
            files_content += file_response.text + "\n\n"

    return files_content

def create_folder(folder):
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)

def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    try:
 
        repo_url = event.get('repo_url')
        branch_name = event.get('branch_name', 'main')
        workspace_url = event['workspace_url']
        
        files_content = ""
        error_message = None

        if repo_url:
            # If repo_url is provided, proceed with fetching the repository
            # Get the VCS secret and token
            gitlab_token = get_secret(VCS_SECRET_NAME)["token"]

            # Fetch the repo content using the GitLab API
            files_content = fetch_files_from_gitlab(repo_url, branch_name, gitlab_token)
            logger.info("Fetched repository files content successfully")

        # Retrieve the API token for Terraform Enterprise
        tfe_api_token = get_secret(TERRAFORM_SECRET_NAME)["tfe_api_token"]

        # Get the workspace, org name, and possibly run ID
        workspace_name, org_name, run_id = get_workspace_id_from_url(workspace_url)

        # Get the latest or specified run error from the Terraform workspace
        error_message = get_latest_run_error(workspace_name, org_name, tfe_api_token, run_id)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "files_content": files_content,
                "error_message": error_message
            })
        }

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }
