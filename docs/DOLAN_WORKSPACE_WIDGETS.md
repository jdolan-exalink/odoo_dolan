# DOLAN Mi Espacio 3.0 — Catálogo de widgets

## Contrato declarativo

Un widget contiene `key`, `type`, `label`, `icon`, `model`, `domain`, `role`, `section`, `tone`, `sizes`, `action` y capacidades que el backend puede verificar. Ninguna configuración cliente determina ACL. Los resultados son construidos por adaptadores de servidor con el usuario y contexto de compañía corrientes.

## Tipos

- `kpi`: conteo/dato resumido y navegación filtrada.
- `alert`: excepción operativa con severidad explícita y persistencia posponer/leído.
- `quick_action`: acción real que se valida al construir el catálogo.
- `pos_status`: sesión real accesible.
- `activity`: registro reciente de adaptador con modelo, id, fecha e icono semántico.
- `summary`: agrupador de KPIs existentes, sin consultas duplicadas.

## Reglas de carga y seguridad

- Verificar `has_access('read')` antes de consultar; no elevar permisos para agregar un widget.
- Aplicar `request.env` y sus record rules/compañías. Enlaces deben volver a respetar las mismas reglas.
- En actividad, leer solo campos de visualización necesarios y limitar el conjunto global a 5–10.
- Cada consulta puede fallar sin romper las demás tarjetas.
- Datos no disponibles deben producir estado vacío o error, nunca valores de muestra.
- Reutilizar `DOLAN_knowledge_bi` para gráficos y consultas BI.
