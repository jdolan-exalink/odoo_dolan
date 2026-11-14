# Rentabilidad (`DOLAN_profitability`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `account`. Para contadores.

## Para qué sirve

Ver el margen bruto de lo vendido por producto, categoría, cliente, vendedor y mes.

## Cómo se calcula

* Base: líneas de producto de facturas y notas de crédito de cliente publicadas (las notas de crédito restan).
* **Ingreso**: importe neto de la línea en la moneda de la empresa.
* **Costo**: cantidad por el costo unitario del producto **guardado al publicar la factura** (campo nuevo en la
  línea). Así el margen de una venta pasada no cambia cuando cambia el costo. Las facturas publicadas antes de
  instalar el módulo usan el costo actual del producto y quedan marcadas como *Costo estimado*.
* **Margen** = ingreso − costo; **margen %** por línea.

## Cómo se usa

*Rentabilidad* abre una tabla dinámica por categoría y mes (ingreso, costo, margen), con gráfico y lista.
Filtros: últimos 12 meses, este mes, margen negativo, costo estimado; agrupación por producto, categoría,
cliente, vendedor y mes.

## Pruebas automáticas

3 tests: margen con el costo al facturar aunque después cambie, nota de crédito que resta, y costo estimado para
líneas sin costo guardado.

## Pendiente

* Margen por sucursal cuando exista el módulo de Sucursales.
* Usar el costo con gastos de importación (ver Costos).
* El margen porcentual de los totales agrupados se calcula mirando margen e ingreso (no se suma).
