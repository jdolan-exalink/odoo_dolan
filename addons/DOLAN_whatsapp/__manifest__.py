{
    'name': 'Envíos y WhatsApp',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Mensajería WhatsApp autohospedada con WAHA, webhooks seguros y registro en contactos',
    'description': '''
DOLAN WhatsApp conecta Odoo Community con un servidor WAHA autohospedado.
Incluye configuración multiempresa, comprobación de conexión, creación de sesión,
emisión manual de mensajes de texto, recepción idempotente de mensajes por webhook
HMAC-SHA512 y una bandeja auditable enlazada con contactos. No depende de servicios
Enterprise ni envía mensajes sin una acción explícita de un usuario.
''',
    'author': 'DOLAN ERP',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/whatsapp_account_views.xml',
        'views/res_config_settings_views.xml',
        'views/whatsapp_message_views.xml',
        'views/res_partner_views.xml',
        'wizard/whatsapp_compose_views.xml',
        'views/whatsapp_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
