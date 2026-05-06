import datetime
import os
import json

LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'atlas_logs.jsonl')

def log_question(user_id, user_text, tool_used, thread_ts):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "user_id": user_id,
        "question": user_text,
        "tool_used": tool_used,
        "thread_ts": thread_ts
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')