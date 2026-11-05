# -*- coding: utf-8 -*-
import json, base64

path = r"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\.system_generated\steps\676\output.txt"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

items = data["normalized_result"]["events"]["items"]
tx_urls = {}
for it in items:
    if it.get("kind") == "request":
        tx_urls[it["transaction_id"]] = it["url"]["url"]
    elif it.get("kind") == "network-content" and it.get("phase") == "response":
        tx_id = it["transaction_id"]
        url = tx_urls.get(tx_id, "")
        if "icon.svg" in url:
            b64 = it.get("body", {}).get("content", "")
            print(f"\n=== {url} ===")
            if b64:
                print(base64.b64decode(b64).decode("utf-8", errors="replace"))
