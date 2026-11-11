# DOLAN Actualización masiva de precios

Addon para Odoo 20 Community pensado para subas frecuentes de precios. Usa los productos y listas de precios nativos de Odoo.

## Funciones

- **Lotes de actualización** (Ventas > Productos > Actualización masiva de precios): por porcentaje, monto fijo o margen sobre el costo.
- **Filtros** por categoría (incluye subcategorías), proveedor (pestaña Compras del producto) y productos puntuales. También se abre desde la lista de productos con *Acción > Actualizar precios en lote*.
- **Destinos**: precio de venta, costo, o precios fijos de una lista de precios.
- **Vista previa** editable antes de aplicar (se puede corregir o quitar un renglón), **redondeo** a múltiplos (1, 10, 100) al más cercano o hacia arriba, y **reversión** de un lote aplicado.
- **Precios atados al dólar**: el producto guarda su precio en USD y el precio de venta en pesos se recalcula con la cotización USD de Odoo. Se puede correr a mano (*Acción > Recalcular precios atados al dólar*) o activar el cron *DOLAN: recalcular precios atados al dólar*. El redondeo se configura en Ajustes.
- **Historial de precios** por producto (botón en la ficha y menú propio) con fecha, usuario, origen, lote y variación.
