from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import os
from anthropic import Anthropic
from dbt_cloud import list_jobs, trigger_job
from bigquery import run_query
import json
from logger import log_question
import time

def safe_say(say, text, thread_ts, retries=3):
    for i in range(retries):
        try:
            return say(text, thread_ts=thread_ts)
        except Exception as e:
            if i < retries - 1:
                time.sleep(2)
            else:
                print(f"Failed to send message after {retries} attempts: {e}")

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

conversation = {}

with open(os.path.join(os.path.dirname(__file__), 'instructions.md'), 'r') as f:
    SYSTEM_PROMPT = f.read()


tools = [
    {
        "name": "list_dbt_jobs",
        "description": (
            "Lists all dbt Cloud jobs for the Maven Lane Analytics project. "
            "Use this when someone asks about available jobs, what jobs exist, "
            "or wants to see their dbt jobs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "trigger_dbt_job",
        "description": (
            "Triggers a dbt Cloud job to run. Use this when someone asks to run, "
            "trigger, or kick off a dbt job. You need the job_id, which you can "
            "get by listing jobs first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "The ID of the dbt job to trigger",
                },
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "run_bigquery_query",
        "description": (
            "Runs a SQL query against the Maven Lane BigQuery data warehouse. "
            "Use this when someone asks about business data like revenue, sales, "
            "SKU performance, inventory, or any metrics. The main table is "
            "Refer to the system instructions for available tables and columns. "
            "Always use fully qualified table names."

        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The BigQuery SQL query to run",
                },
            },
            "required": ["sql"],
        },
    },
]


def process_message(thread_ts, user_text, say, user_id):
    if thread_ts not in conversation:
        conversation[thread_ts] = []
    conversation[thread_ts].append({"role": "user", "content": user_text})
    log_question(user_id, user_text, None, thread_ts)

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            system=SYSTEM_PROMPT,
            max_tokens=1024,
            tools=tools,
            messages=conversation[thread_ts],
        )

        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        conversation[thread_ts].append({"role": "assistant", "content": content})

        if response.stop_reason == "tool_use":
            say("on it, give me a sec...", thread_ts=thread_ts)
            
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "list_dbt_jobs":
                        result = list_jobs()
                    elif block.name == "trigger_dbt_job":
                        result = trigger_job(block.input["job_id"])
                    elif block.name == "run_bigquery_query":
                        result = run_query(block.input["sql"])
                    else:
                        result = {"error": "Unknown tool"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)
                    })
            conversation[thread_ts].append({"role": "user", "content": tool_results})
        else:
            reply = response.content[0].text
            break

    say(reply, thread_ts=thread_ts)


@app.event("app_mention")
def handle_mention(event, say):
    if event.get("bot_id"):
        return
    user_text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])
    process_message(thread_ts, user_text, say, event.get("user", "unknown"))

@app.event("message")
def handle_message(event, say):
    if event.get("bot_id"):
        return
    thread_ts = event.get("thread_ts")
    if thread_ts and thread_ts in conversation:
        user_text = event["text"]
        process_message(thread_ts, user_text, say, event.get("user", "unknown"))

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    handler.start() 

