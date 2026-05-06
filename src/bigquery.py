from google.cloud.bigquery import Client
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(os.path.dirname(__file__), '..', 'bq-service-account.json')

client = Client()

def run_query(sql):
    try:
        results = client.query(sql)
        return [dict(row) for row in results]
    except Exception as e:
        return {"error": str(e)}