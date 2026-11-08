# DOLAN UI 3.1 — auditoría y alcance

Fecha: 2026-11-07. Alcance: `DOLAN_theme`, Odoo 20 CE, Mi Espacio y personalización visual. No se modifica el core de Odoo.

## Base existente

- `dolan_app_drawer.js` centraliza el launcher, preferencias de sesión, tema/paleta/iconos y carga de Mi Espacio.
- `dolan_workspace_3.css` y `dolan_app_drawer.xml` implementan Mi Espacio 3.0 con secciones reordenables, tamaños y contenido configurable por usuario.
- `dolan.screen.preference` conserva tema, densidad, iconos, fondos/colores por empresa y apps ocultas.
- `dolan.workspace.preference` conserva espacios, orden, visibilidad, tamaños y estados.
- `dolan.icon.assignment` y el catálogo local administran equivalencias por aplicación; los recursos se sirven localmente, sin CDN.
- `controllers/workspace.py` expone POS, KPI, actividad y accesos rápidos con permisos del usuario.

## Riesgos y cambios 3.1

| Riesgo | Evidencia | Tratamiento |
|---|---|---|
| KPI con compañías mezcladas | KPI ejecutaba `search_count(definition['domain'])` sin una frontera explícita uniforme | Dominio de `company_id` basado en `request.env.companies`; se omiten modelos sin frontera comprobable. |
| Actividad sin `company_id` propio | `mail.activity` apunta a un registro por `res_model/res_id` | Verificar la compañía del registro enlazado antes del conteo. |
| Contactos compartidos | `res.partner.company_id` puede ser falso | Solo el adaptador de contactos incluye registros compartidos, conforme al modelo de compartición. |
| Preferencias anteriores | Valores nuevos del perfil podrían cambiar el aspecto tras actualizar | Migración `20.0.2.50.0` marca la apariencia existente como `legacy`; no reemplaza modo, densidad, paleta o iconos. |
| Blur costoso | Blur por tarjeta degrada la grilla | Blur solo en superficies principales y fallback CSS; se respeta reducción de transparencia/movimiento. |
| Cache entre empresas | Endpoints actuales no cachean KPIs/actividad en servidor | Se mantiene sin caché compartida; Odoo recarga la acción al cambiar selección de empresas. |

## Límites pendientes de verificar

- Falta ejecutar la matriz multicompañía completa con datos A/B/C, registros compartidos y accesos revocados.
- La previsualización en ajustes es una tarjeta de perfil; todavía no replica el launcher/Mi Espacio real dentro de una vista previa transaccional aplicar/cancelar.
- El conteo de actividades inspecciona hasta 10.000 actividades por consulta; evaluar paginado/agregación SQL si la instancia supera ese volumen.
- Las variantes visuales requieren QA visual en móvil, modo de alto contraste y navegadores sin `backdrop-filter`.
- Compatibilidad con Odoo 21 no está declarada ni verificada.
