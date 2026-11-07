# Auditoría de Mi Espacio DOLAN

Fecha: 2026-11-07
Base revisada: Odoo 20 CE, módulo `DOLAN_theme` en el árbol de trabajo.

## Alcance

Se revisaron la vista de Mi Espacio dentro del app drawer, sus controladores y preferencias, el modelo de escritorio, los estilos del theme, las pruebas existentes y las dependencias de POS, BI, IA y Contabilidad. El alcance es la implementación local; las capturas del PRD son una referencia visual, no evidencia del contenido instalado en cada instancia.

## Inventario de funcionalidades

| Capacidad | Estado observado | Evidencia | Evolución requerida |
|---|---|---|---|
| Mi Espacio dentro del launcher actual | Implementado | `static/src/xml/dolan_app_drawer.xml`, pestaña `mine` | Evolucionar esa vista; no crear un dashboard paralelo |
| KPIs operativos | Parcialmente implementado | `controllers/workspace.py::_kpi_definitions` y `workspace_kpis` | Reagruparlos por prioridad/área y conservar las acciones y dominios |
| Compañías y permisos | Parcialmente implementado | búsquedas con `request.env`, comprobación `has_access('read')` | Añadir pruebas por compañía/grupo y revisar cada adaptador nuevo |
| Filtros por área/rol | Implementado | `WORKSPACE_ROLES`, `role_filter`, `setRoleFilter` | Conservar; ampliar plantilla/espacio sin convertir preferencias visuales en permisos |
| Configuración de indicadores visibles | Implementado parcialmente | `visible_widget_keys`; editor de checks en XML | Incorporar visibilidad y orden de secciones/widgets, modos de indicadores y restauración |
| Posponer / leído | Parcial: estado no sincronizado entre equipos | `_setKpiState` solo escribe `localStorage`; `kpi_states` sí existe en backend y se guarda al restaurar/cargar | Persistir inmediatamente en servidor y evitar ocultar una alerta nueva si crece el conteo |
| Accesos rápidos | Implementado, en bloque separado | bloque `dolan-desktop-quick-actions` y `executeQuickAction` | Integrarlos al layout compacto, hacerlos configurables y ocultar los no disponibles |
| POS | Accesos autorizados a `pos.config` | `workspace_pos_shortcuts` usa entorno normal y `has_access` | Informar estado de sesión real y abrir/continuar solo una sesión accesible, sin crear duplicados |
| Actividad reciente | No encontrada en Mi Espacio | sin endpoint/adaptadores de actividad en `controllers/workspace.py` | Añadir adaptadores limitados, autorizados y con links por modelo |
| Editor de escritorio | Parcial | checks de KPIs y filtro por rol | Agregar visibilidad, orden, tamaños, plantillas y alternativa accesible al drag-and-drop |
| Widgets extensibles | No existe catálogo de componentes | el backend devuelve definiciones KPI fijas; OWL las renderiza en una cuadrícula | Crear registro declarativo compartido entre servidor y cliente, con estados de carga/error |
| Preferencias persistentes | Parcial | `dolan.workspace.preference` guarda rol y widgets; desktop tiene modelos propios | Centralizar configuración del workspace sin migrar ni reemplazar datos del launcher |
| Mi Espacio y BI | Separados | `DOLAN_knowledge_bi` tiene sus propios dashboards | Reutilizar BI para gráficos; no duplicar su motor |
| Theme e iconografía | Disponibles en `DOLAN_theme` | `DolanIcon`, registro/estilo de iconos y tokens | Reutilizar estilo vigente y paletas de sesión |

## Riesgos concretos

1. **Persistencia engañosa de alertas — medio/alto.** Los métodos `snoozeKpi` y `dismissKpi` terminan en `_setKpiState`, que solo usa `localStorage`; la preferencia JSON ya existe pero no se escribe en esos caminos. Posponer/leído desaparecen al usar otra máquina y pueden desalinearse con el backend.
2. **POS sin indicador de sesión — medio.** El endpoint lista `pos.config` accesibles y construye `/pos/ui?config_id=…`, pero no consulta `pos.session`. No puede afirmar caja abierta/cerrada ni seleccionar una sesión activa.
3. **Contadores y acción de actividad.** El KPI de `mail.activity` no entrega dominio (retorna `[]`) y `openKpi` sale sin acción. El botón se presenta como clickeable aunque no navega.
4. **Editor demasiado estrecho.** Solo permite filtrar por rol y marcar KPIs; no edita secciones, accesos, orden o tamaños, ni dispone de plantillas.
5. **Accesos rápidos sin catálogo de disponibilidad.** Los ocho accesos aparecen estáticos; algunas opciones pueden depender de addons o acciones que no estén instalados.
6. **Consultas secuenciales y tolerancia amplia.** KPIs se resuelven individualmente; excepciones se capturan por widget. Esto evita que una consulta rompa el home, pero no mide latencia ni diferencia un fallo temporal de un permiso.
7. **No hay feed común.** No asumir que `mail.message` es un historial universal. Deben consultarse modelos por adaptador y siempre con ACL, record rules y compañías del usuario.

## Decisiones de arquitectura

- Mantener Mi Espacio como la pestaña actual de `DOLAN_theme` y compartir layout, navegación, iconografía y preferencias con el launcher.
- Separar presentación OWL, catálogo de widgets y adaptadores de datos. Los adaptadores corren con el usuario actual y no usan `sudo()` para leer registros de negocio.
- Reutilizar `dolan.workspace.preference` para preferencias de Mi Espacio; ampliar con campos validados en lugar de cambiar los modelos de carpetas/launcher.
- Mantener KPIs como fuentes actuales, dividirlos en áreas visuales sin duplicar consultas ni reglas contables.
- Hacer que el POS consulte sesiones con el acceso del usuario y muestre solo los estados verificables.
- El feed reciente será opt-in por adaptadores (`account.move`, `sale.order`, `res.partner`, `maintenance.request`, `mail.activity` cuando el usuario tenga acceso), con límite pequeño, campos mínimos y navegación validada.
- Los widgets analíticos complejos delegan en `DOLAN_knowledge_bi`.
- Sin datos demo para rellenar tarjetas. Una consulta ausente o fallida produce estado vacío/error local al widget.

## Matriz de módulos

| Módulo | Relación con Mi Espacio | Riesgo de dependencia |
|---|---|---|
| `DOLAN_theme` | Contenedor OWL, launcher, tokens, iconos y preferencias | APIs internas de web client ya usadas por el theme; mantener adaptadores aislados |
| `DOLAN_pos` | Extiende funciones de POS pero no el resumen de sesiones de Mi Espacio | No depender de modelos de DOLAN si el módulo base de POS basta |
| `DOLAN_knowledge_bi` | Dashboards, KPIs y visualización avanzada | No duplicar su motor ni exigirlo para mostrar el home básico |
| `DOLAN_ai` | Asistente disponible como acceso rápido | La vista debe seguir funcionando si AI no está instalado |
| `DOLAN_accounting` | Indicadores y eventos de facturas/asientos | Consultar solo modelos y campos autorizados; compañías activas |

## Compatibilidad y reversión

No se modificará el core de Odoo. Los nuevos campos serán aditivos y tendrán valores por defecto compatibles. La migración debe conservar `role_filter`, `visible_widget_keys` y `kpi_states`. Una reversión del código debe poder renderizar esos campos antiguos sin transformarlos; las nuevas preferencias pueden volver a defaults sin eliminar el diseño guardado previamente.

## Cierre de auditoría

La base funcional es reutilizable, pero el estado de persistencia de alertas y el del POS no alcanza los criterios del PRD. La implementación debe empezar por corregir esos contratos, definir las preferencias del widget layout y añadir adaptadores de actividad antes de cerrar la QA visual.
