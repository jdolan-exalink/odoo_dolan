{
    'name': 'DOLAN Auditoría',
    'version': '20.0.1.0.0',
    'summary': 'Bitácora inalterable de operaciones sensibles: precios, CUIT, cuentas bancarias, anulaciones, pagos, conciliaciones y permisos',
    'description': """
Auditoría
=========

* Registra quién, cuándo, en qué empresa, sobre qué registro y con qué valores
  antes y después se hicieron operaciones sensibles.
* Viene configurada para: precios y costos de productos e ítems de listas de
  precios, CUIT y datos fiscales de contactos, cuentas bancarias, cambios de
  estado de comprobantes (anulación, vuelta a borrador), pagos, conciliaciones,
  usuarios y sus permisos, y borrados de esos registros.
* Las reglas se pueden ajustar (qué campos y qué operaciones).
* La bitácora no se puede modificar ni borrar desde la interfaz; nunca guarda
  contraseñas, claves, tokens ni datos de tarjeta.
* Si la operación se hace con un motivo (contexto dolan_audit_reason), queda
  registrado.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['account', 'product'],
    'data': [
        'security/audit_security.xml',
        'security/ir.access.csv',
        'data/audit_rules.xml',
        'views/audit_views.xml',
    ],
    'installable': True,
    'application': True,
}
