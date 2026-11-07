#!/usr/bin/env python3
"""Append verified upstream source references for the DOLAN icon catalog."""

import hashlib
import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "addons/DOLAN_theme/static/src/lib"
EMOJI = {
    "invoicing": ("Receipt", "receipt"), "sales": ("Chart increasing", "chart_increasing"),
    "utilities": ("Toolbox", "toolbox"), "crm": ("Handshake", "handshake"),
    "pos": ("Convenience store", "convenience_store"), "dashboards": ("Bar chart", "bar_chart"),
    "ai": ("Robot", "robot"), "expenses": ("Purse", "purse"), "articles": ("Books", "books"),
    "attendance": ("Alarm clock", "alarm_clock"), "calendar": ("Tear-off calendar", "tear-off_calendar"),
    "livechat": ("Headphone", "headphone"), "accounting": ("Abacus", "abacus"),
    "purchases": ("Shopping bags", "shopping_bags"), "contacts": ("Card index dividers", "card_index_dividers"),
    "conversations": ("Speech balloon", "speech_balloon"), "events": ("Admission tickets", "admission_tickets"),
    "inventory": ("Package", "package"), "activities": ("Clipboard", "clipboard"),
    "lunch": ("Fork and knife", "fork_and_knife"), "maintenance": ("Wrench", "wrench"),
    "manufacturing": ("Factory", "factory"), "email_marketing": ("Envelope", "envelope"),
    "sms_marketing": ("Mobile phone", "mobile_phone"), "kitchen": ("Cooking", "cooking"),
    "projects": ("Rocket", "rocket"), "repairs": ("Hammer and wrench", "hammer_and_wrench"),
    "subscriptions": ("Repeat button", "repeat_button"), "workshop": ("Hammer", "hammer"),
    "vacations": ("Beach with umbrella", "beach_with_umbrella"), "rentals": ("Key", "key"),
    "link_tracker": ("Link", "link"), "barcode": ("Card file box", "card_file_box"),
    "surveys": ("Ballot box with ballot", "ballot_box_with_ballot"), "data_cleaning": ("Broom", "broom"),
    "recruitment": ("Briefcase", "briefcase"), "fleet": ("Automobile", "automobile"),
    "applications": ("Puzzle piece", "puzzle_piece"), "whatsapp": ("Telephone receiver", "telephone_receiver"),
    "printer": ("Printer", "printer"), "scale": ("Balance scale", "balance_scale"),
    "payment_terminal": ("Credit card", "credit_card"), "settings": ("Gear", "gear"),
    "employees": ("Office worker", "office_worker"),
}
SYSTEM = {
    "invoicing": "receipt", "sales": "chart_multiple", "utilities": "toolbox", "crm": "handshake",
    "pos": "store_microsoft", "dashboards": "data_bar_vertical", "ai": "bot", "expenses": "wallet",
    "articles": "book_open", "attendance": "clock", "calendar": "calendar", "livechat": "headset",
    "accounting": "calculator", "purchases": "shopping_bag", "contacts": "contact_card", "conversations": "chat",
    "events": "ticket_diagonal", "inventory": "box", "activities": "clipboard_task", "lunch": "food",
    "maintenance": "wrench", "manufacturing": "building_factory", "email_marketing": "mail", "sms_marketing": "phone",
    "kitchen": "food_pizza", "projects": "rocket", "repairs": "wrench_screwdriver", "subscriptions": "arrow_sync",
    "workshop": "building_shop", "vacations": "beach", "rentals": "key", "link_tracker": "link",
    "barcode": "barcode_scanner", "surveys": "poll_horizontal", "data_cleaning": "broom_sparkle",
    "recruitment": "briefcase_search", "fleet": "vehicle_car", "applications": "apps_list_detail",
    "whatsapp": "chat_multiple", "printer": "document_print", "scale": "scales", "payment_terminal": "payment",
    "settings": "settings", "employees": "person",
}
COMMITS = {
    "emoji": "1ffb34c752ecf5d402f04cfb4b392c77f57c54bc",
    "system": "e15fc0de25fab983e3e42bac8798be69a85c23bf",
}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--emoji-repo", required=True, type=Path, help="Clon local de microsoft/fluentui-emoji en el commit fijado")
parser.add_argument("--system-repo", required=True, type=Path, help="Clon local de microsoft/fluentui-system-icons en el commit fijado")
args = parser.parse_args()
EMOJI_REPO = args.emoji_repo
SYSTEM_REPO = args.system_repo


def exists(repo, source):
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"HEAD:{source}"], capture_output=True).returncode == 0


catalog = json.loads((LIB / "dolan_icon_catalog.json").read_text(encoding="utf-8"))
manifest_path = LIB / "icon_asset_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
existing = {entry["local_path"] for entry in manifest.get("assets", [])}
new, missing = [], []
for app in catalog["apps"]:
    key = app["id"].removeprefix("app.")
    folder, stem = EMOJI[key]
    prefix = f"assets/{folder}/" + ("Default/" if key == "employees" else "")
    for variant, local, suffix in (("3D", f"fluent_3d/{key}.png", "3d.png"), ("Flat", f"fluent_flat/{key}.svg", "flat.svg")):
        source_stem = "tear-off_calendar" if key == "calendar" else stem
        source = f"{prefix}{variant}/{source_stem}_{suffix}"
        if key == "employees":
            source = f"{prefix}{variant}/office_worker_{'3d_default.png' if variant == '3D' else 'flat_default.svg'}"
        if not exists(EMOJI_REPO, source):
            missing.append(source)
            continue
        new.append(("fluent_emoji", COMMITS["emoji"], source, local))
    name = SYSTEM[key]
    size = "20" if key == "data_cleaning" else "24"
    for variant, local in (("filled", f"fluent_filled/{key}.svg"), ("regular", f"fluent_regular/{key}.svg")):
        source = f"assets/{name.replace('_', ' ').title()}/SVG/ic_fluent_{name}_{size}_{variant}.svg"
        if key == "employees":
            source = f"assets/Person/SVG/ic_fluent_person_24_{variant}.svg"
        if not exists(SYSTEM_REPO, source):
            missing.append(source)
            continue
        new.append(("fluent_system_icons", COMMITS["system"], source, local))

if missing:
    raise SystemExit("Missing pinned upstream files:\n" + "\n".join(missing))
for library, commit, source, local in new:
    if local in existing:
        continue
    path = LIB / local
    manifest["assets"].append({
        "library": library,
        "commit": commit,
        "upstream_path": source,
        "local_path": local,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Catalog assets recorded: {len(new)}; total manifest entries: {len(manifest['assets'])}")
