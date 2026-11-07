# DOLAN Mi Espacio 3.0 — PRD de implementación

Fecha: 2026-11-07. Referencia funcional: `docs/DOLAN_WORKSPACE_AUDIT.md` y PRD original aportado por el usuario.

## Objetivo

Evolucionar la pestaña existente Mi Espacio del launcher de DOLAN a un centro operativo responsive, personalizable y conectado a datos reales, manteniendo los KPIs, accesos, filtros y preferencias existentes.

## Alcance funcional

- Cabecera contextual con usuario/espacio y hora local.
- Filtros Todo, Administración, Ventas, Compras, Depósito, Producción y Mantenimiento, persistiendo último espacio.
- Tarjeta POS solo si hay terminales permitidas; estado de sesión verificado desde Odoo.
- Accesos rápidos configurables, sujetos a presencia de módulos/acciones.
- Áreas de atención, resumen, otros indicadores y actividad reciente.
- Modos Prioridades, Completo y Personalizado.
- Editor para visibilidad/orden/tamaños de widgets con opción accesible sin drag-and-drop.
- Temas, iconos, contrastes y responsive heredados de DOLAN UI.
- Migración aditiva desde preferencias actuales y reversión compatible.

## No objetivos

- Un dashboard BI paralelo.
- Datos simulados, sesiones POS creadas automáticamente o elevación de permisos.
- Modificar el core de Odoo.
- Convertir plantillas visuales en grupos/permisos de seguridad.

## Fases y aceptación

1. **Auditoría:** inventario y riesgos documentados.
2. **Design system/layout:** evolución del componente actual y estados responsivos.
3. **Datos:** adaptadores KPI/actividad, persistencia del estado y permisos.
4. **POS:** estado de sesiones autorizado y apertura segura.
5. **Actividad reciente:** adaptadores mínimos, límite de resultados y enlaces válidos.
6. **Personalización:** guardar diseño, tamaño, accesos y modos.
7. **QA/migración:** pruebas de usuario/compañía/módulos ausentes, temas, pantallas y actualización.

El estado de cada fase se anota en `docs/DOLAN_WORKSPACE_TESTS.md`. No se declara completa una fase hasta tener evidencia automatizada o manual registrada.
