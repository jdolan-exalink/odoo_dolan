{
    'name': 'DOLAN Mesa de ayuda',
    'version': '20.0.1.0.0',
    'summary': 'Tickets de soporte con equipos, etapas, SLA, correo entrante y aviso por WhatsApp',
    'description': """
Mesa de ayuda
=============

* Tickets numerados por empresa con cliente, equipo, responsable, prioridad,
  canal (correo, WhatsApp, teléfono, web o mostrador) y etiquetas.
* Equipos con miembros, horario laboral y alias de correo: cada correo que
  llega al alias abre un ticket y las respuestas siguen en el mismo hilo.
* Etapas configurables; las de cierre registran fecha y motivo.
* Reglas de SLA por equipo y prioridad con vencimiento calculado sobre el
  horario del equipo; el estado (en término, en riesgo, vencido, cumplido) se
  actualiza al avanzar el ticket y con una tarea programada.
* Aviso al cliente por WhatsApp desde el ticket si DOLAN_whatsapp está instalado
  (el mensaje lo revisa y envía una persona).
* Separación por empresa en todos los modelos.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Services/Helpdesk',
    'depends': ['mail', 'resource'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.access.csv',
        'data/helpdesk_data.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_config_views.xml',
        'views/helpdesk_menus.xml',
    ],
    'installable': True,
    'application': True,
}
