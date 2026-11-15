# Tienda online (`DOLAN_ecommerce`)

Carpeta del Inicio: **Comercial**. Estado: beta. Depende de `website_sale`, `website_sale_stock` y
`payment_mercado_pago`. Perfil Completo.

> Instalarla instala el sitio web de Odoo: queda una página pública en `/` y la tienda en `/shop`. Antes de
> instalarla en un servidor de producción hay que decidir el dominio y el diseño.

## Para qué sirve

Vender por internet con los mismos productos, precios y stock del sistema, cobrando con Mercado Pago.

## Cómo se usa

1. **Tienda online → Configuración → Configurar tienda** (responsables de ventas): elegir las categorías a
   publicar. Opciones: solo productos con stock (los servicios se publican igual), armar las categorías de la
   tienda a partir de las categorías de producto, vender sin stock o no, y mostrar «quedan N» a partir de cierta
   cantidad. Se puede repetir sin duplicar categorías.
2. En la lista de productos, acciones **Publicar en la tienda** y **Sacar de la tienda**.
3. **Configuración → Mercado Pago**: cargar las credenciales de la cuenta y activar el medio de pago.
4. **Pedidos web**: los pedidos que entran por la tienda, con su pago y entrega como cualquier pedido de venta.
5. **Ver la tienda** abre `/shop`.

Los cupones y promociones de la web salen de **Fidelización** (`website_sale_loyalty` se instala solo).

## Pruebas automáticas

4 tests: publicación por categoría solo con stock y categorías de la tienda sin duplicar, publicación sin filtro de
stock y sin categoría, acciones de publicar y sacar y acceso a Mercado Pago, configuración solo para responsables.

## Pendiente

* Promociones del motor DOLAN en la web (hoy son solo del POS).
* Envío con costo por zona.
* Precios de la tienda desde Listas de precios DOLAN.
* Plantilla visual de la tienda con la marca del cliente.
