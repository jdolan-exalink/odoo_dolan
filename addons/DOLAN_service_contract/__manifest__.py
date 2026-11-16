{
    'name': 'DOLAN Contratos',
    'version': '20.0.1.0.0',
    'summary': 'Contratos de servicio con vigencia, renovación y ajuste de precio por índice (IPC, ICL, CER) o porcentaje',
    'description': """
Contratos
=========

* Contrato con cliente, vigencia, responsable, documento firmado y notas.
* Renovación automática por N meses o vencimiento, con aviso al responsable
  antes del fin.
* Ajuste periódico del importe: porcentaje fijo o índice (IPC, ICL, CER, CAC u
  otro que se cargue), con desfase de publicación configurable; cada ajuste
  queda en un historial con índices, factor e importes.
* Si el contrato está vinculado a una suscripción de DOLAN_subscription, el
  ajuste actualiza también los precios de sus líneas: la facturación sigue
  siendo la de Suscripciones, sin duplicarla.
* Separación por empresa.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Services/Contracts',
    'depends': ['mail', 'DOLAN_subscription'],
    'data': [
        'security/contract_security.xml',
        'security/ir.access.csv',
        'data/contract_data.xml',
        'views/contract_views.xml',
    ],
    'installable': True,
    'application': True,
}
