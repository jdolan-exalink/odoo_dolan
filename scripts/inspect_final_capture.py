# -*- coding: utf-8 -*-
import json, base64

path = r"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\.system_generated\steps\622\output.txt"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

steps = data["normalized_result"]["steps"]
for s in steps:
    print(f"Step {s['step_index']} ({s['step_id']}): status={s['status']}, error={s['error']}")
    sc = s.get("artifacts", {}).get("screenshot", {})
    if sc.get("state") == "captured":
        val = sc.get("value", sc)
        b64 = val.get("data_base64")
        if b64:
            out_png = rf"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\dolan_final_{s['step_index']}_{s['step_id']}.png"
            with open(out_png, "wb") as pf:
                pf.write(base64.b64decode(b64))
            print(f"  Saved screenshot: {out_png}")

events = data["normalized_result"]["events"]["items"]
print(f"\nTotal console / page-error events: {len(events)}")
for ev in events:
    print("  EVENT:", ev)
