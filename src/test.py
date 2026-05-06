import requests
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

account_id = os.environ.get("DBT_CLOUD_ACCOUNT_ID")
token = os.environ.get("DBT_CLOUD_API_TOKEN")

url = f"https://sp904.us1.dbt.com/api/v2/accounts/{account_id}/jobs/"
headers = {"Authorization": f"Token {token}"}

r = requests.get(url, headers=headers)
print(r.status_code)
print(r.json())