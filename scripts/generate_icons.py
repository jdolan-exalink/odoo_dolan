import pathlib
import struct
import zlib

ADDONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "addons"

PALETTES = {
    "DOLAN_base": ("#714B67", "#017E84", "DB"),
    "DOLAN_theme": ("#714B67", "#9C6ADE", "UI"),
    "DOLAN_l10n_ar_afip": ("#1A73E8", "#52B4FF", "AR"),
    "DOLAN_accounting": ("#008818", "#017E84", "AC"),
    "DOLAN_ai": ("#714B67", "#FF6B6B", "AI"),
    "DOLAN_ocr": ("#0180A5", "#00B4D8", "OC"),
    "DOLAN_views": ("#5C6AC4", "#47C1BF", "VW"),
    "DOLAN_pos": ("#D23F3A", "#F4A261", "PS"),
    "DOLAN_stock_mrp": ("#9A6B01", "#E9C46A", "SM"),
    "DOLAN_subscription": ("#017E84", "#2A9D8F", "SB"),
    "DOLAN_renting": ("#8E44AD", "#BB8FCE", "RN"),
    "DOLAN_knowledge_bi": ("#2B6CB0", "#4299E1", "KB"),
}


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def make_png(c1_hex: str, c2_hex: str, size: int = 128) -> bytes:
    r1, g1, b1 = hex_to_rgb(c1_hex)
    r2, g2, b2 = hex_to_rgb(c2_hex)
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            s = (x + y) / max(2 * (size - 1), 1)
            r = int(r1 * (1 - s) + r2 * s)
            g = int(g1 * (1 - s) + g2 * s)
            b = int(b1 * (1 - s) + b2 * s)
            dx = min(x, size - 1 - x)
            dy = min(y, size - 1 - y)
            rad = 22
            alpha = 255
            if dx < rad and dy < rad:
                dist_sq = (rad - dx) ** 2 + (rad - dy) ** 2
                if dist_sq > rad**2:
                    alpha = 0
            cx, cy = size // 2, size // 2
            if abs(x - cx) < 26 and abs(y - cy) < 26 and ((x - cx) ** 2 + (y - cy) ** 2 < 28**2):
                r, g, b = 255, 255, 255
            row.extend((r, g, b, alpha))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    for mod, (c1, c2, label) in PALETTES.items():
        desc = ADDONS_DIR / mod / "static" / "description"
        desc.mkdir(parents=True, exist_ok=True)
        (desc / "icon.png").write_bytes(make_png(c1, c2))
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">\n'
            f'  <defs>\n'
            f'    <linearGradient id="g_{mod}" x1="0%" y1="0%" x2="100%" y2="100%">\n'
            f'      <stop offset="0%" stop-color="{c1}"/>\n'
            f'      <stop offset="100%" stop-color="{c2}"/>\n'
            f'    </linearGradient>\n'
            f'  </defs>\n'
            f'  <rect x="6" y="6" width="88" height="88" rx="20" fill="url(#g_{mod})"/>\n'
            f'  <text x="50" y="60" text-anchor="middle" font-family="Inter, Arial, sans-serif" '
            f'font-size="32" font-weight="700" fill="#ffffff">{label}</text>\n'
            f'</svg>\n'
        )
        (desc / "icon.svg").write_text(svg, encoding="utf-8")
    print(f"OK: Generados {len(PALETTES)} icon.png e icon.svg en {ADDONS_DIR}")


if __name__ == "__main__":
    main()
