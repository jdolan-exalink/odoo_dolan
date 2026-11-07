#!/usr/bin/env python3
"""Read and validate the shared DOLAN distribution source lock."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load_lock(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    if data.get("schema_version") != 1:
        errors.append("schema_version debe ser 1")
    odoo = data.get("odoo", {})
    if not re.fullmatch(r"[0-9a-f]{40}", str(odoo.get("commit", ""))):
        errors.append("commit Odoo inválido")
    repos = data.get("ingadhoc", [])
    if not repos:
        errors.append("no hay repositorios IngAdhoc")
    names = set()
    for repo in repos:
        name = repo.get("name", "")
        if not name or name in names:
            errors.append(f"nombre de repositorio vacío o repetido: {name!r}")
        names.add(name)
        if not re.fullmatch(r"[0-9a-f]{40}", str(repo.get("commit", ""))):
            errors.append(f"commit inválido para {name}")
        if not repo.get("repository", "").startswith("https://github.com/"):
            errors.append(f"origen Git no permitido para {name}")
    images = data.get("images", {})
    required_images = {
        "odoo_base", "odoo_installer_base", "postgres", "waha", "whisper_base", "escpos_base",
    }
    if set(images) != required_images:
        errors.append("el inventario de imágenes no coincide con las seis imágenes base/servicio esperadas")
    for name, image in images.items():
        if not image.get("reference") or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(image.get("digest", ""))):
            errors.append(f"digest de imagen inválido o ausente: {name}")
    if errors:
        raise ValueError("; ".join(errors))
    return data


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock_path = root / "distribution.lock.json"
    try:
        lock = load_lock(lock_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"distribution lock inválido: {exc}", file=sys.stderr)
        return 2

    dockerfile = root / "Dockerfile"
    docker_source = dockerfile.read_text(encoding="utf-8") if dockerfile.is_file() else ""
    match = re.search(r"^ARG ODOO_REF=([0-9a-f]{40})$", docker_source, re.MULTILINE)
    if not match or match.group(1) != lock["odoo"]["commit"]:
        print("distribution lock inválido: ODOO_REF del Dockerfile no coincide", file=sys.stderr)
        return 2

    def locked_reference(name: str) -> str:
        image = lock["images"][name]
        return f"{image['reference']}@{image['digest']}"

    source_refs = {
        "Dockerfile": ("odoo_base", root / "Dockerfile"),
        "plantilla Dockerfile": ("odoo_installer_base", root / "installer/templates/Dockerfile.odoo"),
        "Whisper": ("whisper_base", root / "services/local-whisper/Dockerfile"),
        "ESC/POS": ("escpos_base", root / "services/escpos-bridge/Dockerfile"),
    }
    for label, (image_name, source_path) in source_refs.items():
        source = source_path.read_text(encoding="utf-8")
        if f"FROM {locked_reference(image_name)}" not in source:
            print(f"distribution lock inválido: base de imagen no coincide en {label}", file=sys.stderr)
            return 2

    runtime_sources = (
        root / "docker-compose.yml", root / "crear_odoo20.sh", root / "crear_odoo20.ps1",
        root / ".github/workflows/ci.yml",
    )
    for image_name in ("postgres", "waha"):
        reference = locked_reference(image_name)
        for source_path in runtime_sources:
            if reference not in source_path.read_text(encoding="utf-8"):
                print(f"distribution lock inválido: {reference} no coincide en {source_path.relative_to(root)}", file=sys.stderr)
                return 2

    if len(sys.argv) == 2 and sys.argv[1] == "adhoc":
        for item in lock["ingadhoc"]:
            print(f"{item['name']}\t{item['repository']}\t{item['commit']}")
        return 0
    if len(sys.argv) != 1:
        print("Uso: distribution_lock.py [adhoc]", file=sys.stderr)
        return 2

    print(f"Lock válido: Odoo {lock['odoo']['series']} {lock['odoo']['commit']}")
    print(f"IngAdhoc fijado: {len(lock['ingadhoc'])} repositorios")
    image_values = lock.get("images", {}).values()
    pinned_images = sum(bool(item.get("digest")) for item in image_values)
    print(f"Imágenes fijadas por digest: {pinned_images}/{len(lock.get('images', {}))}")
    print(f"Estado global: {lock.get('lock_status', 'desconocido')}")
    if lock.get("lock_status") != "complete":
        print("Pendiente: locks Python/APT y checksum de wkhtmltopdf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
