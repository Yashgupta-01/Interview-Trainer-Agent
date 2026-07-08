import os
import requests
from dotenv import load_dotenv

load_dotenv()
WATSONX_API_KEY = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")

print("Key starts with:", WATSONX_API_KEY[:5] if WATSONX_API_KEY else None)
print("Project ID:", WATSONX_PROJECT_ID)

token_url = "https://iam.cloud.ibm.com/identity/token"
headers = {"Content-Type": "application/x-www-form-urlencoded"}
data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={WATSONX_API_KEY}"

print("Fetching IAM token...")
token_resp = requests.post(token_url, headers=headers, data=data)
if token_resp.status_code != 200:
    print("IAM Token failed:", token_resp.text)
    exit(1)

access_token = token_resp.json().get("access_token")
print("Got IAM Token!")

ml_url = "https://au-syd.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
ml_headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}
payload = {
    "input": "Hello world",
    "parameters": {
        "decoding_method": "greedy",
        "max_new_tokens": 50,
        "temperature": 0.5
    },
    "model_id": "meta-llama/llama-3-3-70b-instruct",
    "project_id": WATSONX_PROJECT_ID
}

print("Calling Watsonx...")
resp = requests.post(ml_url, headers=ml_headers, json=payload)
print("Status Code:", resp.status_code)
if resp.status_code != 200:
    print("Error:", resp.text)
else:
    print("Success:", resp.json()['results'][0]['generated_text'])
