# Auditoría de productos, promociones y POS — Fase A

**Proyecto:** `jdolan-exalink/odoo_dolan`
**Fecha:** 2026-11-05
**Plataforma objetivo:** Odoo 20 Community Edition
**Revisión de código:** commit `097d18ed92e9df308041addad3facd4e671516a2` (`github-export`, sincronizado con `origin/main` al iniciar la auditoría)
**Runtime QA:** imagen local `dolan/odoo20-ce-rea:20.0`; PostgreSQL 17; base aislada `dolan_products_audit_20261105`.

## Alcance y reglas de evidencia

Esta entrega cierra la auditoría previa al desarrollo de lógica comercial. Se revisaron manifiestos, modelos, vistas, seguridad, JavaScript, README y pruebas de `DOLAN_pos`, `pos_scale_management`, `DOLAN_stock_mrp`, `DOLAN_payment_terminal` y `ePOS_print`; también los módulos Odoo 20 relacionados con POS, productos, códigos de barras, descuentos, lealtad, RR. HH. y stock.

No se importó información real, no se modificó la base de producción, no se inició ningún cobro y no se comunicó con balanzas ni terminales físicas. La auditoría no inspeccionó datos de clientes, comprobantes o credenciales. La base QA se creó vacía y se usó solo para instalar módulos y correr pruebas automatizadas existentes.

Estados de la matriz:

- **Completo:** hay evidencia suficiente de que el requisito queda cubierto en el alcance indicado.
- **Parcial:** existe una parte utilizable, pero falta integración, validación, seguridad o evidencia.
- **Ausente:** no se encontró implementación aplicable.
- **No aplicable:** fuera del objetivo o resuelto por diseño.
- **No verificable:** requiere hardware, credenciales, comportamiento de navegador o evidencia externa a esta auditoría.

La disponibilidad de una función nativa no equivale a que esté configurada en cada POS. La presencia de un addon o su instalación tampoco prueba su funcionamiento de extremo a extremo.

## Resumen ejecutivo

1. **Productos y precios:** reutilizar `product.template`, `product.product`, unidades, impuestos y `product.pricelist`. No hace falta un segundo maestro de productos ni otra tabla de listas de precios. El código de balanzas ya consulta esos modelos.
2. **POS:** el núcleo nativo de Odoo proporciona catálogo, productos, métodos de pago, descuentos de línea/globales, promociones/lealtad, cajeros y control de precios. `pos_discount`, `pos_loyalty` y `pos_hr` se instalaron correctamente en QA; en la base local principal `pos_discount` y `pos_loyalty` figuran desinstalados. Las configuraciones reales de POS no se validaron.
3. **Gap central confirmado:** no existe `addons/DOLAN_discount_engine`. No hay campañas DOLAN con calendario, condiciones por medio de pago confirmado, beneficios de empleados, cupos, autorización de supervisor, auditoría append-only ni reportes antifraude.
4. **Balanzas:** `pos_scale_management` ofrece catálogo por equipo/sucursal, excepciones y listas, perfiles de códigos, previsualización y exportación auditable. El resolver implementa excepción vigente → lista de balanza/sucursal → precio estándar. El perfil Kretz/iTegra está bloqueado; no se encontró serializador de producción. La lectura del perfil de etiqueta no está conectada al lector de artículos del POS.
5. **Terminales:** DOLAN configura Clover y Mercado Pago, pero el código disponible no demuestra conexión de descuento a pago finalizado ni conciliación POS. Las pruebas Mercado Pago usan token `mock` y devuelven resultado simulado; no prueban el proveedor. Clover requiere verificación física; esta auditoría no hizo un cobro.
6. **Calidad:** los módulos relevantes se instalaron en una base limpia QA. La suite automatizada dio **0 fallos de aserción y 1 error de preparación**: `DOLAN_pos.tests.test_pos.TestDolanPos.setUpClass` busca `account.tax.group.l10n_ar_vat_afip_code`, campo inexistente en este runtime. Los tests de balanzas ejecutados cubren reglas y un adaptador sintético, no hardware ni el formato comercial de Kretz/iTegra.

## Entorno reproducible y resultado

### Base local existente (lectura de metadatos de módulos únicamente)

Odoo reportó versión `20.0`, con addon paths de Odoo, DOLAN e IngAdhoc. Se consultaron únicamente estado y versión de los módulos, sin abrir registros comerciales:

| Módulo | Estado en base local | Versión informada |
|---|---|---|
| `point_of_sale` | instalado | `20.0.1.0.2` |
| `DOLAN_pos` | instalado | `20.0.1.2.0` |
| `pos_scale_management` | instalado | `20.0.1.0.0` |
| `DOLAN_payment_terminal` | instalado | `20.0.1.0.0` |
| `ePOS_print` | instalado | `20.0.1.0.0` |
| `barcodes` | instalado | `20.0.2.0` |
| `pos_hr` | instalado | `20.0.1.0` |
| `pos_discount` | desinstalado | `20.0.1.0` |
| `pos_loyalty` | desinstalado | `20.0.2.0` |
| `stock_barcode` | no instalable en el registro de módulos | `20.0.1.0` |

La fila `stock_barcode` no se debe interpretar como capacidad disponible en esta instancia: el estado es `uninstallable` y no se halló su fuente en las rutas de addons consultadas. El addon DOLAN de operaciones de inventario tiene otras dependencias y no es prueba de sustitución funcional dentro del POS.

### Base limpia QA

Se creó `dolan_products_audit_20261105`, sin clonar la base local. Instalación terminada correctamente para:

`point_of_sale`, `pos_restaurant`, `hr`, `stock`, `barcodes`, `pos_discount`, `pos_loyalty`, `pos_hr`, `DOLAN_pos`, `pos_scale_management`, `DOLAN_payment_terminal` y `ePOS_print`.

Las versiones del runtime coinciden con las informadas en la tabla anterior. El tag de imagen del contenedor no está fijado a un digest; para reproducibilidad fuerte el despliegue debe fijar tanto el digest de imagen como el commit de addons.

### Pruebas ejecutadas

Comando de carga de la QA (la opción `--without-demo` produjo un aviso por recibir `all`; Odoo interpretó el booleano como verdadero):

```text
odoo-bin -c /etc/odoo/odoo.conf -d dolan_products_audit_20261105 \
  -i point_of_sale,pos_restaurant,hr,stock,barcodes,pos_discount,pos_loyalty,pos_hr,\
DOLAN_pos,pos_scale_management,DOLAN_payment_terminal,ePOS_print \
  --without-demo=all --stop-after-init --http-port=0
```

Pruebas seleccionadas:

```text
odoo-bin -c /etc/odoo/odoo.conf -d dolan_products_audit_20261105 \
  -u DOLAN_pos,pos_scale_management --test-enable \
  --test-tags /DOLAN_pos,/pos_scale_management --stop-after-init --http-port=0
```

Resultado: runner `0 failed, 1 error`. El error es de configuración de test, no un fallo de aserción funcional: `addons/DOLAN_pos/tests/test_pos.py:32` usa el dominio `tax_group_id.l10n_ar_vat_afip_code`; Odoo responde `Invalid field account.tax.group.l10n_ar_vat_afip_code`. Debe corregirse en una fase posterior antes de usar esa clase como gate. Los casos de `pos_scale_management` visibles en el log completaron sin error. Los tests de Mercado Pago usan token ficticio `mock`, por lo que no califican como prueba de API real.

## Revisión funcional

### Productos, catálogo y precio

- Los manifiestos DOLAN dependen de los modelos nativos y no crean catálogo paralelo. `pos_scale_management` trabaja con variantes de producto y categorías existentes.
- `PriceResolver.resolve()` calcula vigencia por fecha contextual de Odoo; prioriza excepción por equipo/producto, después la lista configurada en balanza o depósito, y por último `product.lst_price`. Devuelve origen, moneda e impuestos calculados con `taxes.compute_all()`.
- Las excepciones de precio impiden precios negativos, rangos de fecha invertidos y períodos activos superpuestos para equipo/producto. Esto respalda un precio base explícito por equipo; no resuelve promociones, pagos ni descuentos en caja.
- Los perfiles de etiqueta permiten patrón, prefijo, segmentos, cantidad o importe, decimales y verificación EAN-13. Un test interpreta una etiqueta sintética. No existe evidencia de mapeo del código interpretado al modelo de producto durante una venta POS.
- `CatalogResolver` compone inclusión/exclusión por producto/categoría. No se halló implementación específica para múltiples GTIN por producto, GS1 variable completo o trazabilidad de lote/caducidad en tickets POS.
- Odoo nativo tiene variantes, reglas de precios, códigos de barras, empaques, unidades, impuestos, lotes y vencimientos; la auditoría no verificó que cada función esté activada/configurada en la compañía o la caja real.

### POS y cobro

- `DOLAN_pos` extiende cocina/KDS, seguimiento de pedidos, cuenta corriente y métodos Mercado Pago. El manifiesto no añade assets POS OWL propios; no se encontró una UI de promociones DOLAN integrada al carrito.
- Los métodos nativos de descuento, programas promocionales/lealtad y cajeros se pueden instalar desde la distribución examinada. En QA, los módulos se instalaron; `pos_hr` también estaba activo en la base local.
- No se encontró un motor DOLAN para elegibilidad por día/hora/sucursal, descuento ligado al resultado confirmado del adquirente, política de pagos mixtos, cupo de empleado, doble aprobación, reversión proporcional o evidencia por regla/version.
- `DOLAN_payment_terminal` mantiene operaciones de prueba y reserva/idempotencia por equipo y factura. Su flujo Clover usa WebSocket en navegador y token de emparejamiento cifrado; no se encontró en los archivos revisados una capa que convierta una orden POS en pagos contables confirmados para las campañas propuestas.
- `DOLAN_pos` simula éxito de QR/Point cuando el token es `mock`/`test`; el test del estado Point simulado devuelve `COMPLETED`. Prohibir esa configuración en producción y agregar pruebas reales/contratos del proveedor es requisito P0 de la integración, pero el auditor no la cambia en esta fase.
- No se verificó offline, pagos combinados, pago rechazado con descuento condicionado, callback duplicado, devolución parcial, conciliación terminal↔orden ni aislamiento multiempresa del supuesto motor de descuentos, porque ese motor no existe aún.

## Prioridades propuestas para la siguiente fase

### P0 — gates para un MVP seguro de descuentos

1. Corregir el test fiscal fallido y volver a correr sobre una base limpia; conservar la prueba de instalación de todos los módulos relevantes.
2. Definir contrato de dominio y cálculo determinista para campañas/reglas, sin duplicar catálogo ni listas de precios: compatibilidad, orden, prioridad, base imponible, redondeo, fecha/hora de sucursal y snapshot de regla aplicada.
3. Integrar al carrito POS con preview cliente, autoridad final servidor y persistencia de descuentos por línea/orden. El descuento condicionado a tarjeta/QR sólo puede aplicarse si el pago final fue confirmado; evitar caminos `mock` en producción.
4. Diseñar autorización por rol y separación de funciones: límite/motivo obligatorio y autorización de supervisor independiente para excepciones.
5. Añadir auditoría protegida, reglas de acceso y record rules por empresa/POS/sucursal; probar acceso por ORM/RPC y usuario cajero.
6. Definir, antes de codificar, la política de acumulación, pagos mixtos, reintegros, beneficios de empleados, límites y offline. El PRD trae defaults recomendados, pero no decisiones finales para el negocio.
7. Completar regresión de tickets, impuestos argentinos, pagos, devoluciones y arqueo; medir concurrencia/cupos, rendimiento y p95.

### P1 — ampliar productos y canales

- Confirmar barcode/GS1/EAN con la nomenclatura local; integrar códigos de balanza con el flujo POS y pruebas por kilo, importe embebido, dígito de control y redondeo.
- Terminar un adaptador de formato de balanza sólo después de obtener formato exportado/importado por software y modelo real. No habilitar Kretz/iTegra desde el estado actual.
- Conectar proveedor Clover/Mercado Pago a la orden, pagos parciales, cancelación, timeout, idempotencia, reintento y conciliación. Documentar qué instrumento confirma cada API.
- Añadir campañas a Ventas/Facturación usando la misma semántica sólo después de consolidar la interfaz de dominio del POS.
- Reportes por empresa/sucursal/caja/cajero/campaña/producto/medio con separación de métricas contables y operativas.

### P2 — extensiones

- Alertas de patrones anómalos, campañas masivas, promociones combinadas y casos de carga. Optimizar sólo con perfilado sobre dataset/concurrencia representativos.

## Límites y decisiones abiertas

- Sin una balanza conectada no se valida formato de etiqueta real, PLU, formato de exportación, impuestos ni firmware. El adaptador Kretz/iTegra permanece bloqueado con buen criterio.
- Sin pagos/claves de sandbox de los proveedores no se valida el resultado final del adquirente, webhooks, instrumentos o reembolsos. No se realizó un cobro de prueba.
- Falta aprobación funcional de: acumulación día+medio+empleado; descuento en pagos mixtos; límites e identificación de empleado beneficiario; aprobación manual; uso offline; tratamiento fiscal de descuento/reintegro.
- La etiqueta Odoo 20 Community no determina por sí sola la licencia del conjunto instalado: los módulos examinados `pos_discount`, `pos_loyalty`, `pos_hr` y `barcodes` declaran LGPL-3 en sus manifiestos locales. Mantener atribución/licencia y no reutilizar código o activos privativos.
- El runtime QA confirma que los módulos seleccionados pueden instalarse juntos en esta imagen/commit. No equivale a validación visual del POS, prueba de una sucursal real, desempeño bajo carga o certificación fiscal.

## Referencias oficiales Odoo 20

- [Variantes de producto](https://www.odoo.com/documentation/20.0/applications/sales/sales/products_prices/products/variants.html)
- [Listas de precios y reglas](https://www.odoo.com/documentation/20.0/applications/sales/sales/products_prices/prices/pricing.html)
- [Métodos de pago del POS](https://www.odoo.com/documentation/20.0/applications/sales/point_of_sale/payment_methods.html)
- [Códigos de descuento y nomenclatura de barras](https://www.odoo.com/documentation/20.0/applications/sales/point_of_sale/pricing/discount_tags.html)
- [Descuentos y programas promocionales/lealtad (manual Odoo 20)](https://www.odoo.com/documentation/20.0/id/applications/sales/point_of_sale/extra/pricing.html)
- [Empleados y permisos del POS](https://www.odoo.com/documentation/20.0/applications/sales/point_of_sale/shop/multicashiers.html)
- [Barcode, EAN, UPC y GS1](https://www.odoo.com/documentation/20.0/applications/inventory_and_mrp/inventory/barcode.html)
- [Nomenclaturas y códigos de peso/precio](https://www.odoo.com/documentation/20.0/applications/inventory_and_mrp/inventory/barcode/operations/barcode_nomenclature.html)
- [Lotes y números de serie](https://www.odoo.com/documentation/20.0/applications/inventory_and_mrp/inventory/product_management/product_tracking.html)
- [Vencimientos y productos perecederos](https://www.odoo.com/documentation/20.0/applications/inventory_and_mrp.html)
- [Compartir productos entre compañías](https://www.odoo.com/documentation/20.0/applications/general/multi_company.html)

## Cierre de Fase A

La Fase A queda documentada con gaps y un entorno de instalación QA reproducible. **No se cierra como “todo listo para desarrollar sin condiciones”**: el test fiscal del addon POS debe repararse y las decisiones de negocio del PRD deben aprobarse antes de la implementación del motor. La próxima entrega debería empezar por el contrato de promociones y sus pruebas, después conectar POS y, por último, medios de pago y balanzas.
