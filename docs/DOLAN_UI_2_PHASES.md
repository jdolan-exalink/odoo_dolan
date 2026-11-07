# DOLAN UI 2.0 — fases de entrega y estado

**Alcance:** aplicar el rediseño al addon `DOLAN_theme`, conservando lógica de negocio y preferencias de escritorio ya guardadas. La iconografía es local, licenciada y seleccionable; no se descargan fuentes desde CDN.

## Estado por fase

| Fase | Entrega | Estado en código | Cierre de aceptación |
|---|---|---|---|
| 0. Auditoría y línea base | Inventario, riesgos, prototipo y matriz | Completada en documentación | Prototipo requiere revisión dentro de Odoo; `file://` fue bloqueado por el navegador compartido. |
| 1. Design System | Tokens semánticos claro/oscuro, tipografía, espacios, estados, radios, sombras, movimiento y foco | Implementada en tokens; integrada inicialmente en launcher y superficies backend comunes | Requiere revisión visual de formularios y apps en runtime claro/oscuro y móvil. |
| 2. Iconografía | Catálogo semántico, 8 tratamientos Fluent y opción de iconos Odoo originales; recursos locales, licencias, fallback y administrador | Implementada en código: 44 apps × 4 familias Fluent, 253 recursos versionados con hashes, alias anteriores preservados y upgrade `20.0.2.33.0` | Requiere ejecutar upgrade QA y aceptar selector, previsualización y cada estilo en launcher/carpetas, claro/oscuro y móvil. |
| 3. Launcher | Persistencia remota prioritaria, tema del sistema, iconos configurables, carpetas, favoritos y densidad | Integrada sobre el launcher actual; no sustituye sus modelos de orden/carpetas | Requiere pruebas E2E mouse/táctil/teclado y sincronización entre dispositivos. |
| 4. Mi Espacio | Preferencias personales de rol, indicadores visibles, estados de leído/posponer y KPIs por ACL | Implementada con modelo por usuario y endpoints autenticados | Requiere validar conteos, reglas de registro y cambios de compañía en Odoo real. |
| 5. POS y accesos | Atajos a POS permitidos por usuario/compañía, usando la ruta nativa | Implementada; consulta `pos.config` con permisos normales, sin `sudo` | Requiere comprobar POS con perfiles, configuración multiempresa y sesiones del runtime. |
| 6. Componentes backend | Tokens en formularios, listas, kanban, menús, diálogos e inputs; fuera del POS transaccional y documentos impresos | CSS por scopes implementado | Requiere inspección de contraste en las apps clave y regresión visual del POS/impresión. |
| 7. QA y entrega | Pruebas, compatibilidad, migración, rollback y revisión de despliegue | Instalación limpia y ORM pasaron en QA; chequeos estáticos completos | Pendiente Hoot en navegador, aceptación visual claro/oscuro/móvil y upgrade de una base existente compatible. No desplegado en localhost ni `10.1.1.9`. |

## Cambios principales

- `DOLAN_theme` agrega tokens de tema, estilos Fluent, opción de iconos Odoo originales, selección global/individual, asignaciones semánticas administrables y preferencias personales de Mi Espacio.
- La opción individual de iconos permanece bloqueada hasta que un administrador habilite “Permitir preferencia individual” en Ajustes → DOLAN UI.
- Los SVG y PNG seleccionados se guardan en el addon y traen un manifiesto de procedencia, licencia y SHA-256; no se permite ingresar una URL de icono desde el administrador.
- Los atajos POS muestran solo configuraciones legibles bajo ACL y las compañías permitidas por el usuario. La apertura continúa por `/pos/ui`.
- Las preferencias existentes de carpetas, posiciones y favoritos permanecen en sus modelos actuales.

## Cómo completar el cierre

1. Actualizar `DOLAN_theme` en una base Odoo 20 de prueba (sin migrar datos de producción).
2. Ejecutar la suite del addon, incluyendo `web.assets_unit_tests` y `TransactionCase`.
3. Recorrer matriz en escritorio y móvil: claro, oscuro, automático; los ocho estilos Fluent y los iconos Odoo originales; permisos y empresas; Mi Espacio; launcher; formularios/listas/diálogos.
4. Confirmar que el POS transaccional, tickets, facturas impresas y periféricos no reciban estilos no deseados.
5. Revisar migración/upgrade, persistencia de asignaciones manuales, respaldo y rollback.
6. Solo entonces aceptar fase 7 y preparar despliegue.

## Validación local disponible

Ejecutar desde la raíz del repositorio:

```powershell
python scripts/check_dolan_ui2.py
git diff --check
```

La suite ORM pasó: 6 post-tests, 0 fallos y 0 errores. La generación de `web.assets_unit_tests` también pasó. Hoot en navegador, revisión visual y upgrade de una base existente siguen pendientes.
