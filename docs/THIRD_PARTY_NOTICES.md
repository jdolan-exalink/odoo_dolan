# Notices de terceros

DOLAN usa bibliotecas y programas de terceros. La lista de esta página está en evolución y no sustituye la revisión de la imagen/SBOM exacta distribuida.

| Componente | Uso | Licencia / entrega |
|---|---|---|
| Odoo Community | ERP base | LGPL-3, sujeto al texto y avisos de la referencia upstream fijada. |
| Addons propios DOLAN | Funciones del producto | LGPL-3, salvo los assets/archivos que indiquen licencia propia en su directorio. |
| pypdfium2 5.10.1 / PDFium | Renderizado PDF del OCR | Pendiente cotejar la metadata y el conjunto completo de avisos del wheel exacto. El build copia los archivos bajo `licenses` del wheel a `/opt/dolan/licenses/pypdfium2`; eso no reemplaza la revisión antes de redistribuir. |
| Microsoft Fluent Emoji | Iconos de aplicaciones en 3D y Flat | MIT; se conserva el aviso de licencia/copyright en `addons/DOLAN_theme/static/src/lib/licenses/FLUENT_EMOJI_LICENSE`. |
| Microsoft Fluent System Icons | Iconos de aplicaciones Filled y Regular | MIT; se incluyen `FLUENT_SYSTEM_ICONS_LICENSE` y `FLUENT_SYSTEM_ICONS_NOTICE` junto a los assets. |
| Tabler Icons | Iconografía local de acciones, controles y compatibilidad | MIT; se conserva `addons/DOLAN_theme/static/src/lib/licenses/TABLER_LICENSE`. |
| IngAdhoc | Localización y módulos comunitarios argentinos | Licencias/avisos dependen de cada repositorio y commit. Las siete fuentes ya tienen commits registrados en `distribution.lock.json`; falta inventariar las licencias por addon y conservar sus notices exactos. |
| wkhtmltopdf | PDF de reportes Odoo | Binario Qt parcheado upstream; incorporar sus avisos exactos al SBOM/notices de release. |
| zxing-cpp 3.1.1 | Lectura de QR/barcodes | Verificar metadata, wheel exacto y avisos transitivos antes del release. |
| WAHA, Whisper, ESC/POS bridge | Servicios Docker | Licencias, versiones y digests deben figurar en SBOM/notices. Whisper y ESC/POS se construyen localmente; WAHA conserva actualmente la etiqueta móvil `latest`. |

## Revisión para cada release

1. Generar SBOM desde los artefactos exactos, no sólo desde requirements fuente.
2. Copiar todos los notices requeridos al paquete binario/imagen y enlazarlos en la ayuda del producto.
3. Verificar licencias transitivas nativas, en especial PDFium y zxing-cpp.
4. Registrar la fuente, versión, digest y licencia efectiva en el manifiesto de release.
5. Revisar obligaciones de redistribución y código correspondiente antes de publicar cada imagen.

Fuentes primarias: [pypdfium2 licensing](https://github.com/pypdfium2-team/pypdfium2#licensing), [pypdfium2 README](https://github.com/pypdfium2-team/pypdfium2), [Odoo license](https://github.com/odoo/odoo/blob/20.0/LICENSE).
