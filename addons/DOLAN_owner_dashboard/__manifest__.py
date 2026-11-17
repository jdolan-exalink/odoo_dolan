{
    'name': 'DOLAN Tablero del dueño',
    'version': '20.0.1.0.1',
    'summary': 'Una sola pantalla con caja y bancos, deuda vencida, pagos de la semana, ventas y margen del mes y alertas',
    'description': """
Tablero del dueño
=================

* Caja y bancos: saldo contable de cada diario de efectivo y banco y el total.
* Clientes: deuda vencida, cuántos clientes deben y los que más deben.
* Proveedores: lo que vence en los próximos 7 días (y lo ya vencido).
* Ventas y margen del mes contra el mes anterior (con Rentabilidad instalada,
  el margen sale del costo guardado en cada factura).
* Alertas de los últimos 7 días y problemas del Diagnóstico.
* Cada bloque abre la pantalla con el detalle. Todo sale de la contabilidad:
  no hay saldos paralelos.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'depends': ['account', 'web'],
    'data': [
        'views/owner_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_owner_dashboard/static/src/js/owner_dashboard.js',
            'DOLAN_owner_dashboard/static/src/xml/owner_dashboard.xml',
            'DOLAN_owner_dashboard/static/src/scss/owner_dashboard.scss',
        ],
    },
    'installable': True,
    'application': True,
}
