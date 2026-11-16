{
    'name': 'DOLAN Agenda de turnos',
    'version': '20.0.1.0.0',
    'summary': 'Turnos de clientes por profesional o recurso, sin superposiciones y con recordatorio',
    'description': """
Agenda de turnos
================

* Servicios con duración y profesionales o recursos (sala, box, equipo) que
  pueden atenderlos, cada uno con su horario laboral.
* Turnos con cliente, estado (reservado, confirmado, atendido, ausente,
  cancelado) y número propio por empresa.
* No deja superponer turnos del mismo profesional ni dar turnos fuera de su
  horario o en sus ausencias.
* Cálculo de horarios libres de un día para un servicio, base para reservar
  desde el portal más adelante.
* Recordatorio automático por correo y, si DOLAN_whatsapp está instalado y el
  servicio lo pide, por WhatsApp; cada envío queda en el turno.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Services/Appointment',
    'depends': ['mail', 'resource'],
    'data': [
        'security/appointment_security.xml',
        'security/ir.access.csv',
        'data/appointment_data.xml',
        'views/appointment_views.xml',
    ],
    'installable': True,
    'application': True,
}
