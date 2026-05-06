from google.cloud.bigquery import Client
import os
import json
import tempfile

credentials_path = os.path.join(os.path.dirname(__file__), '..', 'bq-service-account.json')

if os.path.exists(credentials_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
elif os.environ.get("GOOGLE_CREDENTIALS_JSON"):
    creds = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name

client = Client()

def run_query(sql):
    try:
        results = client.query(sql)
        return [dict(row) for row in results]
    except Exception as e:
        return {"error": str(e)}