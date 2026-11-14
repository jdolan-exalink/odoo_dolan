{
    'name': 'DOLAN Alertas',
    'version': '20.0.1.0.0',
    'summary': 'Avisos por umbral: deuda vencida, pagos de la semana, caja proyectada negativa, diferencias de caja, margen bajo y stock crítico',
    'description': """
Alertas
=======

* Reglas por empresa con un umbral y responsables.
* Tipos: deuda vencida total, clientes con mora mayor a N días, pagos a
  proveedores que vencen en los próximos días, y, si están instalados, caja
  proyectada negativa (Flujo de caja), diferencias de caja a aprobar (Caja y
  Tesorería), productos con margen bajo (Costos) y productos bajo el mínimo
  (Inventario).
* Se revisan cada hora; cuando se dispara una regla se crea una actividad a los
  responsables y, si se pide, un correo. No se repite el aviso hasta que pase el
  tiempo de espera configurado.
* Historial de alertas con valor, umbral y mensaje.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/alert_data.xml',
        'views/alert_views.xml',
    ],
    'installable': True,
    'application': True,
}
