import os
import sys
import base64
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('web/.env.local')
load_dotenv('.env')

nvidia_key = os.getenv('NVIDIA_API_KEY') or (os.getenv('NVIDIA_API_KEYS') or '').split(',')[0].strip()

url = "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/chat-images/ba9c27e8-f62d-452f-8a29-dc77fd092207/6e8b14ce-915c-41d2-a7e8-cb02f61fa0b6/38b77409-8eb1-4e3f-9c98-0fc9c79ec06e.jpg"

print(f"Downloading image from Supabase storage: {url[:70]}...")
img_resp = requests.get(url, timeout=10)
print(f"Image download status: {img_resp.status_code}, length: {len(img_resp.content)} bytes")

# Test 1: NVIDIA NIM with public https:// URL
endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {nvidia_key}",
    "Content-Type": "application/json"
}

body_url = {
    "model": "meta/llama-3.2-11b-vision-instruct",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": "What do you see in this image? Return short summary."},
            {"type": "image_url", "image_url": {"url": url}}
        ]}
    ],
    "max_tokens": 100
}

print("\n--- Test 1: Calling NVIDIA NIM with HTTP URL ---")
try:
    r1 = requests.post(endpoint, headers=headers, json=body_url, timeout=15)
    print("Test 1 status:", r1.status_code)
    print("Test 1 response:", r1.text[:300])
except Exception as e:
    print("Test 1 exception:", e)

# Test 2: NVIDIA NIM with base64 data URL
b64_data = f"data:image/jpeg;base64,{base64.b64encode(img_resp.content).decode('ascii')}"
body_b64 = {
    "model": "meta/llama-3.2-11b-vision-instruct",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": "What do you see in this image? Return short summary."},
            {"type": "image_url", "image_url": {"url": b64_data}}
        ]}
    ],
    "max_tokens": 100
}

print("\n--- Test 2: Calling NVIDIA NIM with base64 Data URL ---")
try:
    r2 = requests.post(endpoint, headers=headers, json=body_b64, timeout=15)
    print("Test 2 status:", r2.status_code)
    print("Test 2 response:", r2.text[:300])
except Exception as e:
    print("Test 2 exception:", e)
