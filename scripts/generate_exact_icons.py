# -*- coding: utf-8 -*-
import os

ICONS = {
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_knowledge_bi\static\description\icon_knowledge.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M42 15 h28 a4 4 0 0 1 4 4 v48 l-16 -12 l-16 12 z" fill="#00A09D"/>
  <path d="M26 28 h28 a4 4 0 0 1 4 4 v50 l-16 -12 l-16 12 z" fill="#714B67" opacity="0.92"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_subscription\static\description\icon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M50 20 A30 30 0 0 1 80 50" fill="none" stroke="#00A09D" stroke-width="10" stroke-linecap="round"/>
  <path d="M80 50 A30 30 0 0 1 50 80" fill="none" stroke="#00A09D" stroke-width="10" stroke-linecap="round"/>
  <path d="M50 80 A30 30 0 0 1 20 50" fill="none" stroke="#F06050" stroke-width="10" stroke-linecap="round"/>
  <path d="M20 50 A30 30 0 0 1 50 20" fill="none" stroke="#F4A460" stroke-width="10" stroke-linecap="round"/>
  <circle cx="50" cy="20" r="8" fill="#F4A460"/>
  <circle cx="80" cy="62" r="8" fill="#00A09D"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_renting\static\description\icon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M22 78 L54 46" stroke="#00CEB6" stroke-width="12" stroke-linecap="round"/>
  <path d="M22 78 L32 88 M32 68 L40 76" stroke="#00CEB6" stroke-width="8" stroke-linecap="round"/>
  <rect x="46" y="18" width="34" height="34" rx="10" transform="rotate(45 63 35)" fill="#714B67"/>
  <circle cx="67" cy="31" r="5" fill="#FFFFFF"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_ai\static\description\icon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M52 10 C64 10 72 18 72 28 C72 38 64 44 52 44 L42 44 L42 28 C42 18 44 10 52 10 Z" fill="#714B67"/>
  <path d="M22 82 L38 44 L54 82" fill="none" stroke="#714B67" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="28" y1="70" x2="48" y2="70" stroke="#F4A460" stroke-width="9" stroke-linecap="round"/>
  <line x1="72" y1="44" x2="72" y2="82" stroke="#F4A460" stroke-width="10" stroke-linecap="round"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_pos\static\description\icon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="45" cy="32" r="5" fill="#F4A460"/>
  <circle cx="58" cy="38" r="4" fill="#F4A460"/>
  <path d="M22 36 C18 52 34 68 54 66 L78 82" fill="none" stroke="#714B67" stroke-width="10" stroke-linecap="round"/>
  <path d="M22 36 C28 30 48 44 56 58 Z" fill="#F4A460"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_accounting\static\description\icon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="34" cy="34" r="14" fill="#F4A460"/>
  <circle cx="66" cy="66" r="14" fill="#00CEB6"/>
  <line x1="24" y1="76" x2="76" y2="24" stroke="#714B67" stroke-width="12" stroke-linecap="round"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_shopfloor.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="20" y="26" width="46" height="42" rx="8" transform="rotate(-8 43 47)" fill="#1695D8"/>
  <polygon points="36,36 78,66 36,74" fill="#F06050" opacity="0.88"/>
  <polygon points="36,36 62,55 36,68" fill="#1B3A4B"/>
</svg>""",
    r"d:\DEVs\Odoo20-REA\addons\DOLAN_stock_mrp\static\description\icon_barcode.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect x="18" y="22" width="10" height="56" rx="3" fill="#714B67"/>
  <rect x="34" y="22" width="6" height="56" rx="2" fill="#9B6B8E"/>
  <rect x="46" y="22" width="14" height="56" rx="3" fill="#714B67"/>
  <rect x="66" y="22" width="6" height="56" rx="2" fill="#714B67"/>
  <rect x="78" y="22" width="6" height="56" rx="2" fill="#9B6B8E"/>
</svg>""",
}

for path, svg in ICONS.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("Generated SVG:", path)
