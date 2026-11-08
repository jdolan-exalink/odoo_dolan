# DOLAN UI 3.1 — alcance multicompañía

La fuente es `request.env.companies`, es decir, las empresas activas en el contexto efectivo de Odoo. No se usa `res.users.company_ids` como sustituto ni se eleva con `sudo()` para contar datos.

- KPI con `company_id`: dominio explícito `company_id in env.companies.ids`.
- POS: filtra `pos.config.company_id` por empresas activas; sesiones se leen por los POS filtrados.
- Actividad reciente: restringe los registros con compañía y permite contactos compartidos (`company_id=False`) solo en el adaptador de contactos.
- `mail.activity`: comprueba la compañía del registro relacionado; omite enlaces sin compañía verificable.
- Accesos rápidos: solo se publican modelos/acciones con acceso de lectura/escritura disponible; formularios usan contexto activo de Odoo.
- Endpoints no mantienen caché entre usuarios/compañías.

Odoo actualiza la acción/ruta tras confirmar el selector de compañías. La nueva petición obtiene un contexto nuevo y recarga los widgets desde el servidor.
