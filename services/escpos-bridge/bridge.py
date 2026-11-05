#!/usr/bin/env python3
"""Small, fixed-destination ePOS-to-ESC/POS bridge for local POS printers."""

from __future__ import annotations

import base64
import binascii
import os
import socket
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PRINTER_HOST = os.environ.get("PRINTER_HOST", "192.168.1.50")
PRINTER_PORT = int(os.environ.get("PRINTER_PORT", "9100"))
RASTER_WIDTH_DOTS = int(os.environ.get("RASTER_WIDTH_DOTS", "384"))
ALLOWED_ORIGINS = {
    value.strip().rstrip("/")
    for value in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8069,http://localhost:8069",
    ).split(",")
    if value.strip()
}
MAX_BODY = 2 * 1024 * 1024
MAX_IMAGE_HEIGHT = 12000
EPOS_NS = "http://www.epson-pos.com/schemas/2011/03/epos-print"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _bitmap_to_escpos(element: ET.Element) -> bytes:
    try:
        width = int(element.attrib["width"])
        height = int(element.attrib["height"])
        raw = base64.b64decode("".join(_child_text(element).split()), validate=True)
    except (KeyError, ValueError, binascii.Error) as exc:
        raise ValueError("InvalidImage") from exc
    if width < 1 or width > 2048 or height < 1 or height > MAX_IMAGE_HEIGHT:
        raise ValueError("ImageDimensions")
    source_row_bytes = (width + 7) // 8
    if len(raw) < source_row_bytes * height:
        raise ValueError("ImageDataShort")

    target_width = min(RASTER_WIDTH_DOTS, width)
    target_row_bytes = (target_width + 7) // 8
    raster = bytearray(target_row_bytes * height)
    for y in range(height):
        src_row = y * source_row_bytes
        dst_row = y * target_row_bytes
        for x in range(target_width):
            source_x = min(width - 1, int(x * width / target_width))
            bit = (raw[src_row + source_x // 8] >> (7 - source_x % 8)) & 1
            if bit:
                raster[dst_row + x // 8] |= 1 << (7 - x % 8)

    x_bytes = target_row_bytes
    align = element.attrib.get("align", "left").lower()
    alignment = bytes(({"left": 0, "center": 1, "right": 2}.get(align, 0),))
    return (
        b"\x1b\x61" + alignment
        + b"\x1d\x76\x30\x00"
        + bytes((x_bytes & 0xFF, (x_bytes >> 8) & 0xFF, height & 0xFF, (height >> 8) & 0xFF))
        + raster
        + b"\x1b\x61\x00"
    )


def _format_text(element: ET.Element) -> bytes:
    chunks: list[bytes] = []
    align = element.attrib.get("align", "left").lower()
    chunks.append(b"\x1b\x61" + bytes(({"left": 0, "center": 1, "right": 2}.get(align, 0),)))
    if element.attrib.get("bold", "false").lower() == "true":
        chunks.append(b"\x1b\x45\x01")
    chunks.append(_child_text(element).encode("cp858", errors="replace"))
    if element.attrib.get("bold", "false").lower() == "true":
        chunks.append(b"\x1b\x45\x00")
    chunks.append(b"\n")
    return b"".join(chunks)


def translate_epos(payload: bytes) -> bytes:
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("UnsafeXml")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("InvalidXml") from exc

    print_node = next((node for node in root.iter() if _tag(node) == "epos-print"), None)
    if print_node is None:
        raise ValueError("MissingEposPrint")

    output = bytearray(b"\x1b@")
    supported = {"image", "text", "feed", "cut", "pulse"}
    for child in list(print_node):
        name = _tag(child)
        if name not in supported:
            continue
        if name == "image":
            output.extend(_bitmap_to_escpos(child))
        elif name == "text":
            output.extend(_format_text(child))
        elif name == "feed":
            lines = max(0, min(255, int(child.attrib.get("line", "1"))))
            output.extend(b"\x1bd" + bytes((lines,)))
        elif name == "cut":
            # ePOS cut type="feed" means advance to the cutter position, then
            # cut. GS V 65 0 expresses that explicitly on ESC/POS printers.
            output.extend(b"\x1dV\x41\x00")
        elif name == "pulse":
            pin = 1 if child.attrib.get("drawer", "0") == "1" else 0
            output.extend(bytes((0x1B, 0x70, pin, 25, 250)))
    if len(output) <= 2:
        raise ValueError("NoPrintableCommands")
    return bytes(output)


def _response(success: bool, code: str = "", status: int = 0) -> bytes:
    code_attr = f' code="{code}"' if code else ""
    xml = (
        f'<s:Envelope xmlns:s="{SOAP_NS}"><s:Body>'
        f'<response xmlns="{EPOS_NS}" success="{str(success).lower()}"'
        f'{code_attr} status="{status}"/></s:Body></s:Envelope>'
    )
    return xml.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DolanEscposBridge/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin", "").rstrip("/")
        return origin if origin and origin in ALLOWED_ORIGINS else None

    def _write_cors_headers(self, origin: str) -> None:
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        return True

    def do_OPTIONS(self) -> None:
        origin = self._origin()
        self.send_response(204 if origin else 403)
        if origin:
            self._write_cors_headers(origin)
        self.end_headers()

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            body = (
                '{"ok":true,"bridge":"dolan-escpos","printer_host":'
                + repr(PRINTER_HOST).replace("'", '"')
                + f',"printer_port":{PRINTER_PORT},"raster_width_dots":{RASTER_WIDTH_DOTS}'
                + "}"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/cgi-bin/epos/service.cgi":
            self.send_error(404)
            return
        origin = self._origin()
        if not origin:
            self.send_error(403, "Origin not allowed")
            return
        if parse_qs(parsed.query).get("devid", [""])[0] != "local_printer":
            self._send_epos(False, "DeviceNotFound", origin=origin)
            return
        if self.headers.get_content_type() not in ("application/xml", "text/xml", "text/plain"):
            self._send_epos(False, "InvalidContentType", origin=origin)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > MAX_BODY:
            self._send_epos(False, "InvalidPayloadSize", origin=origin)
            return
        try:
            escpos = translate_epos(self.rfile.read(length))
            with socket.create_connection((PRINTER_HOST, PRINTER_PORT), timeout=4) as sock:
                sock.settimeout(4)
                sock.sendall(escpos)
            self._send_epos(True, origin=origin)
        except (OSError, ValueError) as exc:
            code = str(exc) if isinstance(exc, ValueError) else "PRINTER_NOT_REACHABLE"
            self.log_message("print error: %s", code)
            self._send_epos(False, code, origin=origin)

    def _send_epos(self, success: bool, code: str = "", origin: str | None = None) -> None:
        body = _response(success, code)
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if origin:
            self._write_cors_headers(origin)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if RASTER_WIDTH_DOTS < 1 or RASTER_WIDTH_DOTS > 1024:
        raise SystemExit("RASTER_WIDTH_DOTS must be 1..1024")
    server = ThreadingHTTPServer(("0.0.0.0", 8765), Handler)
    server.daemon_threads = True
    print(
        f"ePOS-to-ESC/POS bridge listening on :8765 -> {PRINTER_HOST}:{PRINTER_PORT} "
        f"({RASTER_WIDTH_DOTS} dots)",
        flush=True,
    )
    server.serve_forever()
