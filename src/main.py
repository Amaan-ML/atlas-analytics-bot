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

def safe_say(say, text, thread_ts=None, retries=3):
    for i in range(retries):
        try:
            if thread_ts:
                return say(text, thread_ts=thread_ts)
            else:
                return say(text)
        except Exception as e:
            if i < retries - 1:
                time.sleep(2)
            else:
                print(f"Failed to send message after {retries} attempts: {e}")

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Fetch bot's own user ID so we can detect @mentions in DM messages
BOT_USER_ID = None
try:
    auth_response = app.client.auth_test()
    BOT_USER_ID = auth_response["user_id"]
    print(f"Bot user ID: {BOT_USER_ID}")
except Exception as e:
    print(f"Could not fetch bot user ID: {e}")

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


def process_message(convo_key, user_text, say, user_id, thread_ts=None):
    """
    convo_key:  unique key for conversation history storage.
    thread_ts:  the Slack thread timestamp to reply into.
    """
    if convo_key not in conversation:
        conversation[convo_key] = []
    conversation[convo_key].append({"role": "user", "content": user_text})
    log_question(user_id, user_text, None, convo_key)

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            system=SYSTEM_PROMPT,
            max_tokens=1024,
            tools=tools,
            messages=conversation[convo_key],
        )

        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        conversation[convo_key].append({"role": "assistant", "content": content})

        if response.stop_reason == "tool_use":
            safe_say(say, "on it, give me a sec...", thread_ts=thread_ts)

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
            conversation[convo_key].append({"role": "user", "content": tool_results})
        else:
            reply = response.content[0].text
            break

    safe_say(say, reply, thread_ts=thread_ts)


@app.event("app_mention")
def handle_mention(event, say):
    """Handles @mentions in channels (Slack sends these as app_mention events)."""
    if event.get("bot_id"):
        return
    user_text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])
    process_message(thread_ts, user_text, say, event.get("user", "unknown"), thread_ts=thread_ts)


@app.event("message")
def handle_message(event, say):
    """
    Handles:
    1. @mentions in DMs (Slack sends these as message events, not app_mention)
    2. Follow-up messages in any existing thread (channels or DMs)
    """
    if event.get("bot_id"):
        return
    if event.get("subtype"):
        return

    user_text = event.get("text", "")
    thread_ts = event.get("thread_ts")

    # Check if bot was @mentioned in the message text
    bot_mentioned = BOT_USER_ID and f"<@{BOT_USER_ID}>" in user_text

    if bot_mentioned and not thread_ts:
        # New @mention (in DM) — start a new thread from this message
        msg_ts = event["ts"]
        process_message(msg_ts, user_text, say, event.get("user", "unknown"), thread_ts=msg_ts)
    elif thread_ts and thread_ts in conversation:
        # Follow-up in an existing thread — continue the conversation
        process_message(thread_ts, user_text, say, event.get("user", "unknown"), thread_ts=thread_ts)


if __name__ == "__main__":
    try:
        handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
        handler.start()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()