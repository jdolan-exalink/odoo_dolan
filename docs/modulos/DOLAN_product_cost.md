# Costos (`DOLAN_product_cost`)

Carpeta del Inicio: **Inventario y Compras**. Estado: beta. Depende de `purchase`.

## Para qué sirve

Saber cuánto cuesta reponer cada producto, cuándo y a quién se le compró por última vez y qué margen deja el
precio de venta, con alertas cuando el margen queda por debajo del mínimo de su categoría.

## Cómo funciona

* **Última compra**: al confirmar un pedido de compra se guardan, por producto y empresa, el precio (neto del
  descuento, en la moneda de la empresa y por unidad del producto), la fecha y el proveedor, y queda en el
  historial.
* **Costo de reposición**: por defecto toma la última compra; en el producto se puede pasar a *Manual* y cargarlo
  a mano (también queda en el historial).
* **Margen**: sobre el precio de venta, con el costo de reposición o con el costo promedio de Odoo según elija cada
  empresa (Empresa → pestaña Costos). Si no hay costo de reposición se usa el promedio.
* **Margen mínimo** en la categoría de producto; las subcategorías sin valor heredan el de la superior.

## Pantallas

* Producto → pestaña **Costos**: costo promedio, origen y valor del costo de reposición, última compra, margen e
  historial.
* **Costos → Análisis de márgenes**: una fila por producto vendible y empresa con precio, costo promedio, costo de
  reposición, cuánto más cuesta reponer que el promedio, margen y mínimo. Filtros: margen bajo, costo mayor al
  precio, reponer cuesta más que el promedio, sin compras. Se recalcula todos los días o con *Actualizar*.
  *Actualizar precios de los seleccionados* abre la actualización masiva de **DOLAN Listas de precios** (no se
  duplica esa función).
* **Costos → Historial de costos**: todos los cambios, con variación porcentual y proveedor.

## Permisos

Usuarios de Compras leen el análisis y el historial; responsables de Compras pueden borrarlos. Filtrado por
empresa. Los costos de reposición y la última compra son por empresa.

## Pruebas automáticas

6 tests: última compra actualiza reposición e historial, descuento neto, reposición manual que no se pisa, margen
según la base elegida, alerta con mínimo heredado de la categoría, acceso del comprador.

## Pendiente

* Gastos de importación prorrateados: usar `stock_landed_costs` de Odoo (no instalado) y llevar el resultado al
  costo de reposición.
* Costo de reposición en dólares con la cotización del día (`DOLAN_exchange`).
* Aviso cuando un proveedor sube el costo por encima de un porcentaje.
