# DOLAN Mercado Libre y Tiendanube

Conector de marketplaces para Odoo 20 Community. Menú: Ventas > Marketplaces.

## Puesta en marcha

**Mercado Libre**
1. Crear una aplicación en el portal de desarrolladores de Mercado Libre.
2. En Odoo, crear la cuenta, copiar la *URL de redirección OAuth* y la *URL de notificaciones* que muestra la ficha y cargarlas en la app (tópico `orders_v2`).
3. Cargar App ID y clave secreta y tocar **Conectar con Mercado Libre**. El token se renueva solo.

**Tiendanube**
1. Cargar el ID de la tienda, el access token de la app, la clave secreta (firma los webhooks) y un correo de contacto (lo exige la API).
2. Registrar los webhooks `order/paid` y `order/cancelled` con la URL de notificaciones.
3. Tocar **Probar conexión**.

## Qué hace

- **Leer publicaciones**: trae publicaciones y variantes y las vincula a productos de Odoo por SKU (referencia interna). Las que no coinciden se vinculan a mano en la lista.
- **Enviar stock y precios**: stock libre del depósito elegido menos la reserva, y precio de la lista de precios (con IVA si la cuenta publica precios finales). Tarea programada cada 30 minutos.
- **Bajar ventas**: ventas pagadas pasan a pedidos confirmados, con el comprador dado de alta (Consumidor Final si no informa CUIT). Opcionalmente factura sola; si la factura falla (por ejemplo ARCA), el pedido queda con el error a la vista. Tarea cada 10 minutos más las notificaciones en tiempo real.
- **Registro de sincronización** con cada operación y sus errores.

Las cancelaciones posteriores quedan anotadas en el pedido para revisarlas; no se anula nada automáticamente.
