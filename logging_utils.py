import json

def log_user(msg):
    print(f"🧑‍💬 {msg}")

def log_assistant(msg):
    print(f"🤖 {msg}")

def log_tool_call(name, input_data):
    print(f"🛠️  {name}: {input_data}")

def log_tool_result(res):
    print(f"📦 → {json.dumps(res, ensure_ascii=False)}") 