import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('.env')

from huggingface_hub import HfApi

token = os.getenv('HF_TOKEN')
api = HfApi(token=token)

print("Fetching logs from weeasdwee/AI_BOT...")
gen = api.fetch_space_logs('weeasdwee/AI_BOT')
all_logs = []
for chunk in gen:
    all_logs.append(chunk)

full_log = "".join(all_logs)
lines = full_log.splitlines()

os.makedirs("logs", exist_ok=True)
with open("logs/hf_space.log", "w", encoding="utf-8") as f:
    f.write(full_log)

print(f"Total log lines: {len(lines)}")
print(f"Saved to logs/hf_space.log")

# Print the last 100 lines
print("\n--- Last 80 lines ---")
for l in lines[-80:]:
    print(l)
