# Recursos locales de DOLAN UI

El launcher no usa CDN. Las aplicaciones se resuelven por IDs semánticos en `dolan_icon_catalog.json` y reciben 3D, Flat, Filled, Regular u original de Odoo.

- Fluent Emoji: Microsoft `fluentui-emoji`, commit `1ffb34c752ecf5d402f04cfb4b392c77f57c54bc`.
- Fluent System Icons: Microsoft `fluentui-system-icons`, commit `e15fc0de25fab983e3e42bac8798be69a85c23bf`.
- Tabler Icons: commit `8d4fecf58167041e6ddccd9b06a08a17b4154030`.
- Licencias y avisos upstream: `licenses/`.
- Origen, ruta instalada y SHA-256: `icon_asset_manifest.json`.

Las variantes Soft, Limpio y Duotono se componen con CSS sobre SVG/PNG originales. `python scripts/check_dolan_ui2.py` valida integridad, seguridad SVG, unicidad dentro de cada familia y catálogo semántico.
