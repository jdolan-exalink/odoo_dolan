# -*- coding: utf-8 -*-
import json, base64

path = r"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\.system_generated\steps\686\output.txt"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

for s in data["normalized_result"]["steps"]:
    sc = s.get("artifacts", {}).get("screenshot", {})
    if sc.get("state") == "captured" and s["step_id"] == "home-menu-icons-1to1":
        b64 = sc["value"]["data_base64"]
        out_png = r"C:\Users\juan\.gemini\antigravity\brain\02377eab-40e6-432b-85d2-bf2b3e53061c\dolan_home_menu_icons_1to1.png"
        with open(out_png, "wb") as pf:
            pf.write(base64.b64decode(b64))
        print("Saved:", out_png)
