# -*- coding: utf-8 -*-
import json, base64

path = r"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\.system_generated\steps\669\output.txt"
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
        if "ir.ui.menu" in url:
            b64 = it.get("body", {}).get("content", "")
            if b64:
                raw = base64.b64decode(b64).decode("utf-8", errors="replace")
                rj = json.loads(raw)
                res = rj.get("result", [])
                for m in res:
                    wdata = m.get("web_icon_data", "")
                    decoded_preview = ""
                    if wdata:
                        try:
                            dec = base64.b64decode(wdata).decode("utf-8", errors="replace")
                            if "<svg" in dec:
                                decoded_preview = dec
                            else:
                                decoded_preview = f"<binary PNG {len(wdata)} chars>"
                        except Exception as e:
                            decoded_preview = str(e)
                    print(f"\n=== {m['name']} (web_icon={m['web_icon']}) ===")
                    print(decoded_preview[:1500])
