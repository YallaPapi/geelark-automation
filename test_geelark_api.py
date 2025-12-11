"""
Test Geelark API connection - list all cloud phones
"""
import os
import uuid
import time
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://openapi.geelark.com"
APP_ID = os.getenv("GEELARK_APP_ID")
API_KEY = os.getenv("GEELARK_API_KEY")
TOKEN = os.getenv("GEELARK_TOKEN")


def get_headers_key_auth():
    """Generate headers for key-based authentication"""
    trace_id = str(uuid.uuid4()).upper().replace("-", "")
    timestamp = str(int(time.time() * 1000))
    nonce = trace_id[:6]

    # sign = SHA256(appId + traceId + ts + nonce + apiKey).upper()
    sign_string = APP_ID + trace_id + timestamp + nonce + API_KEY
    sign = hashlib.sha256(sign_string.encode()).hexdigest().upper()

    return {
        "Content-Type": "application/json",
        "appId": APP_ID,
        "traceId": trace_id,
        "ts": timestamp,
        "nonce": nonce,
        "sign": sign
    }


def get_headers_token_auth():
    """Generate headers for token-based authentication"""
    trace_id = str(uuid.uuid4()).upper().replace("-", "")

    return {
        "Content-Type": "application/json",
        "traceId": trace_id,
        "Authorization": f"Bearer {TOKEN}"
    }


def list_phones():
    """List all cloud phones"""
    url = f"{API_BASE}/open/v1/phone/list"

    # Try token auth first
    headers = get_headers_token_auth()
    data = {"page": 1, "pageSize": 10}

    print(f"Calling {url}")
    print(f"Headers: {headers}")

    resp = requests.post(url, json=data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:1000]}")

    if resp.status_code == 200:
        result = resp.json()
        if result.get("code") == 0:
            items = result.get("data", {}).get("items", [])
            print(f"\nFound {len(items)} cloud phones:")
            for phone in items:
                print(f"  - {phone.get('serialName')} (ID: {phone.get('id')}, Status: {phone.get('status')})")
            return items

    # If token auth fails, try key auth
    print("\nToken auth failed, trying key auth...")
    headers = get_headers_key_auth()
    resp = requests.post(url, json=data, headers=headers)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:1000]}")

    if resp.status_code == 200:
        result = resp.json()
        if result.get("code") == 0:
            items = result.get("data", {}).get("items", [])
            print(f"\nFound {len(items)} cloud phones:")
            for phone in items:
                print(f"  - {phone.get('serialName')} (ID: {phone.get('id')}, Status: {phone.get('status')})")
            return items

    return []


if __name__ == "__main__":
    list_phones()
