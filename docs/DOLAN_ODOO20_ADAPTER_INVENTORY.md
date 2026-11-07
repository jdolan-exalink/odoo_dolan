# P2 — Inventario de dependencias con APIs de Odoo 20

**Fecha:** 2026-11-07  
**Estado:** inventario inicial completado; sin cambios funcionales ni extracción de adaptadores.  
**Alcance:** patches OWL, herencias de plantillas, imports frontend y overrides POS/contabilidad visibles en los addons de la distribución.

## Hallazgos priorizados

| Área | Evidencia en el checkout | Riesgo | Verificación disponible | Siguiente paso propuesto |
|---|---|---:|---|---|
| Launcher / Workspace | `addons/DOLAN_theme/static/src/xml/dolan_app_drawer.xml:4-53` extiende `web.NavBar.AppsMenu`; `static/src/js/dolan_app_drawer.js` importa `web.core.registry`, hooks y RPC. | Alto | `addons/DOLAN_theme/static/tests/dolan_app_drawer.test.js`; instalación y tests de backend Theme en CI. | Encapsular el registro y lectura de menús/preferencias en un adaptador web con prueba OWL de apertura, render, favoritos y carpetas. |
| ARCA, formulario de contactos | `addons/DOLAN_l10n_ar_afip/static/src/js/padron_form_draft.js:9` parchea `FormController.prototype`; el botón se inyecta en `static/src/xml/out_invoice_list.xml` sobre `account.AccountMoveListView.Buttons`. | Alto | Tests Python de padrón/seguridad; no se encontró prueba JS específica de botón/form controller. | Definir una pequeña interfaz de adaptador para el formulario y cubrir el click, RPC, carga del borrador y errores sin guardar. |
| POS, promociones y autorización | `addons/DOLAN_discount_engine/static/src/app/dolan_discount_pos.js:131,145,161,363,370,392` parchea `Orderline`, `PosOrderline`, `PosStore`, `ProductScreen`, `PaymentScreen` y `ControlButtons`; dos XML extienden templates POS. | Muy alto | Tests Python del motor; no se encontró test OWL/POS en el addon. | Extraer primero un contrato POS: aplicar/deshacer descuento, aprobación de supervisor, reconexión y rehidratación del pedido. Mantener el comportamiento actual mientras se añade test de integración POS. |
| POS, lectura de balanza | `addons/pos_scale_management/static/src/app/scale_barcode_pos.js:35` parchea `ProductScreen.prototype`; importa el módulo interno `@point_of_sale/app/screens/product_screen/product_screen`. | Alto | Suite Python de balanzas; no se encontró test JS de scanner/pantalla. | Usarlo como piloto de adaptador POS acotado después de fijar una prueba JS de barcode y fallback sin balanza. |
| ePOS / impresoras | `addons/ePOS_print/static/src/js/epos_print_test.js` depende de registry/action plugin, hooks y `@point_of_sale/app/utils/init_lna`; `views/epos_print_views.xml` hereda formularios y ajustes POS. | Alto | La acción de prueba es frontend; no se encontró test JS de impresora. | Separar transporte local (LNA/WebSocket/bridge) de UI y fijar contrato de impresión/prueba; incluir matriz Epson, ESC/POS y permiso de red local. |
| Contabilidad | `addons/DOLAN_accounting/views/accounting_menus.xml:92-99` modifica el kanban de diarios y sustituye el botón nativo `JournalBodySalePurchase/action_create_new`; varios modelos extienden `account.move`, `account.payment`, `res.partner` y diarios. | Muy alto | Tests ORM de contabilidad e instalación limpia; no cubren todas las vistas ni navegación multicompañía. | Crear una capa de servicios para las operaciones contables propias; primero añadir pruebas de visibilidad/navegación multicompañía sobre la vista heredada. |

## Clases de dependencia encontradas

1. **Assets JS de Odoo:** imports `@web/*`, `@point_of_sale/*` y `@mail/*`. Son módulos públicos del bundle, pero rutas/clases concretas pueden cambiar entre versiones mayores.
2. **Parche de prototipos OWL:** afecta comportamiento por monkey patch y es sensible a cambios de firma, orden de carga y nombres de métodos.
3. **Herencia QWeb/OWL por nombre y XPath:** depende de identificadores y estructura DOM del upstream; los XPaths deben verificarse contra las vistas de la serie fijada.
4. **Extensión ORM:** `_inherit` agrega campos/comportamiento sin copiar el core; el riesgo está en hooks y dependencias de orden, no en un fork del núcleo.

## Límites y decisión de arquitectura

- El escaneo confirma patches OWL explícitos en Theme, ARCA, descuentos y balanzas. Los demás hallazgos de Odoo frontend incluyen imports directos, actions y herencias XML.
- No se modifica ni se copia el código del núcleo Odoo. La fuente permanece fijada por commit/digest.
- No se crea todavía un addon adaptador vacío: hacerlo sin definir contratos de llamadas y pruebas sólo trasladaría acoplamiento.
- El primer piloto sugerido es el lector de balanza POS, de superficie pequeña; antes de moverlo se añadirá una prueba JS que capture su conducta actual. El segundo candidato será el launcher, dado que ya tiene una prueba OWL existente.
- Descuento POS y contabilidad quedan como dominios de riesgo alto; no deben migrarse hasta tener pruebas de ciclo completo y multicompañía.

## Gate para empezar extracción

Para cada piloto: (a) prueba que falla si cambia el comportamiento observable; (b) contrato del adaptador que sólo use datos/eventos explícitos; (c) implementación Odoo 20 aislada; (d) prueba de assets/OWL en CI; (e) comparación visual o evidencia UI para los cambios de Theme/POS. No declarar compatibilidad Odoo 21 hasta repetir el gate con el código y las pruebas de esa serie.
