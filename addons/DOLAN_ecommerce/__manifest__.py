{
    'name': 'DOLAN Tienda online',
    'version': '20.0.1.0.1',
    'summary': 'Tienda web sobre el eCommerce de Odoo: publicación por categoría, stock en línea y cobro con Mercado Pago',
    'description': """
Tienda online
=============

* App propia en el Inicio con lo que hace falta para la tienda: pedidos web,
  productos publicados, Mercado Pago, configuración y acceso a la tienda.
* Asistente «Configurar tienda»: publica los productos de las categorías
  elegidas (opcionalmente solo los que tienen stock), arma las categorías de
  la tienda a partir de las categorías de producto y define si se vende sin
  stock y si se muestra la cantidad disponible.
* Acciones «Publicar en la tienda» y «Sacar de la tienda» en la lista de
  productos.
* Usa el eCommerce de Odoo (``website_sale``), el stock en línea
  (``website_sale_stock``) y el medio de pago Mercado Pago
  (``payment_mercado_pago``). Los cupones y promociones web salen de
  Fidelización (``website_sale_loyalty``, se instala solo).
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Website/Website',
    'depends': ['website_sale', 'website_sale_stock', 'payment_mercado_pago'],
    'data': [
        'security/ir.access.csv',
        'views/ecommerce_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}
