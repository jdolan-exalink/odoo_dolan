# -*- coding: utf-8 -*-
{
    'name': 'DOLAN - Límite de crédito con bloqueo',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Bloqueo de ventas al exceder el límite de crédito, cheques en cartera como riesgo y autorización de excepciones',
    'description': """
Cuenta corriente con límite de crédito
======================================

Extiende el límite de crédito nativo de Odoo (Contabilidad > Ajustes > Límite de
crédito de ventas), que sólo muestra un aviso:

* Modo por empresa: sólo avisar o bloquear la confirmación del pedido.
* Riesgo del cliente = saldo de cuenta corriente + pedidos sin facturar +
  cheques de terceros en cartera que todavía no vencieron (opcional).
* Bloqueo manual del crédito de un cliente.
* Grupo "Autorizar ventas sobre el límite de crédito" para excepciones, que
  quedan registradas en el pedido.
* Con el módulo DOLAN_credit_limit_pos el mismo control aplica a las ventas en
  cuenta corriente del Punto de Venta.
""",
    'license': 'LGPL-3',
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ar/odoo20-rea',
    'depends': ['sale', 'account'],
    'data': [
        'security/dolan_credit_limit_security.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
