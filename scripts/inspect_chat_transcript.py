import sys, os
sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
import requests, json
from dotenv import dotenv_values

v = dotenv_values('.env')
url = v['SUPABASE_URL']
key = v['SUPABASE_SERVICE_ROLE_KEY']
headers = {'apikey': key, 'Authorization': f'Bearer {key}'}

sid = 'b5dcedf7-71c5-4f29-becf-a7ac40523ddd'

# 1. Fetch session
r_s = requests.get(f"{url}/rest/v1/ai_chat_sessions?id=eq.{sid}", headers=headers)
print("=== SESSION METADATA ===")
print(json.dumps(r_s.json(), indent=2, ensure_ascii=False))

# 2. Fetch all messages with full fields
r_m = requests.get(f"{url}/rest/v1/ai_chat_messages?session_id=eq.{sid}&order=created_at.asc", headers=headers)
msgs = r_m.json()
print(f"\nTotal messages in session: {len(msgs)}")
for idx, m in enumerate(msgs):
    role = m.get("role", "").upper()
    created = m.get("created_at")
    meta = {k: v for k, v in m.items() if k != "content"}
    print(f"\n======================================================")
    print(f"MESSAGE {idx+1}: [{role}] at {created}")
    print(f"Metadata: {json.dumps(meta, ensure_ascii=False)}")
    print("--- CONTENT ---")
    print(m.get("content"))
