{
    'name': 'DOLAN Logística: aviso de entrega por WhatsApp',
    'version': '20.0.1.0.0',
    'summary': 'Avisa al cliente por WhatsApp cuando se entrega su pedido',
    'description': """
Aviso de entrega por WhatsApp
=============================

* En la hoja de ruta, la opción «Avisar por WhatsApp al entregar» (viene
  marcada si la empresa tiene «Avisar las entregas por WhatsApp» en su ficha).
* Al registrar una entrega completa o parcial se manda un WhatsApp al cliente
  con el número de entrega y quién recibió, por la cuenta de DOLAN WhatsApp de
  la empresa. Si el envío falla, la entrega se registra igual y el error queda
  en la parada.
* Se instala solo cuando están Logística y DOLAN WhatsApp.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'depends': ['DOLAN_logistics', 'DOLAN_whatsapp'],
    'data': ['views/delivery_route_views.xml'],
    'installable': True,
    'auto_install': True,
}
