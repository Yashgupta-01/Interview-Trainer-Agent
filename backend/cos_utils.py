import os
import ibm_boto3
from ibm_botocore.client import Config, ClientError

# Configuration - Replace with your IBM Cloud Object Storage credentials
COS_ENDPOINT = "https://s3.us-south.cloud-object-storage.appdomain.cloud" # Adjust region as needed
COS_API_KEY_ID = os.getenv("COS_API_KEY_ID", "your_api_key_here")
COS_INSTANCE_CRN = os.getenv("COS_INSTANCE_CRN", "your_instance_crn_here")
BUCKET_NAME = "interview-trainer-data-bucket"

# Create resource
try:
    cos = ibm_boto3.resource("s3",
        ibm_api_key_id=COS_API_KEY_ID,
        ibm_service_instance_id=COS_INSTANCE_CRN,
        config=Config(signature_version="oauth"),
        endpoint_url=COS_ENDPOINT
    )
except Exception as e:
    print(f"Error creating COS resource: {e}")

def upload_dataset(file_path, item_name):
    print(f"Uploading {file_path} to bucket: {BUCKET_NAME}, key: {item_name}")
    try:
        cos.Bucket(BUCKET_NAME).upload_file(file_path, item_name)
        print(f"File Uploaded Successfully.")
    except ClientError as be:
        print("CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        print("Unable to upload file: {0}".format(e))

if __name__ == "__main__":
    dataset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'processed', 'questions.jsonl')
    if os.path.exists(dataset_path):
        upload_dataset(dataset_path, "questions.jsonl")
    else:
        print(f"Dataset not found at {dataset_path}")
