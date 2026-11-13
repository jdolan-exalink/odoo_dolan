# Mesa de ayuda (`DOLAN_helpdesk`)

Carpeta del Inicio: **Servicios**. Estado en el catálogo: beta (implementado, pendiente de QA funcional).
Depende de `mail` y `resource`. Perfiles del instalador: Servicios y Completo.

## Para qué sirve

Registrar y seguir las consultas y reclamos de clientes como tickets, con plazos de atención (SLA) y avisos.

## Cómo se usa

1. **Configuración → Equipos**: crear el equipo (viene uno, «Soporte»), sus miembros, el horario laboral y el
   alias de correo (por ejemplo `soporte@empresa`). Cada correo que llega al alias abre un ticket y las respuestas
   quedan en el mismo hilo.
2. **Reglas de SLA** (en el equipo): horas para resolver según la prioridad mínima y, si se quiere, etiquetas.
   Si aplican varias, gana la de mayor prioridad y menor plazo. El plazo se cuenta sobre el horario del equipo.
3. **Tickets**: tablero por etapa con barra de SLA. Botones *Tomar* (me lo asigno) y *Avisar por WhatsApp*
   (abre el envío de DOLAN WhatsApp con un texto propuesto; lo revisa y envía una persona).
4. Para pasar a una etapa de cierre (*Resuelto* o *Cancelado*) hay que escribir la **Solución**.

Estados del SLA: *En término*, *En riesgo* (queda menos del porcentaje de aviso de la regla), *Vencido* y
*Cumplido*. Se actualizan al cambiar el ticket y cada 30 minutos.

Asignación: *Manual* o *balanceada* (al miembro con menos tickets abiertos).

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.helpdesk.ticket` | Ticket: número `TK-año-#####`, cliente, equipo, responsable, prioridad, canal, etiquetas, SLA, solución. |
| `dolan.helpdesk.team` | Equipo con alias de correo, miembros, horario, asignación. |
| `dolan.helpdesk.stage` | Etapas (globales o por equipo); las de cierre registran fecha. |
| `dolan.helpdesk.sla` | Reglas de SLA por equipo. |
| `dolan.helpdesk.tag` | Etiquetas. |

## Permisos

* **Usuario**: ve, crea y edita tickets de sus empresas; ve equipos y reglas.
* **Responsable**: además configura equipos, etapas y SLA y puede borrar tickets.
* Todo filtrado por empresa (`company_ids`).

## Pruebas automáticas

9 tests (`tests/test_helpdesk.py`): numeración, elección de SLA, estados del SLA en el tiempo, cierre con
solución, asignación balanceada, alta por correo, aislamiento entre empresas y permisos.

## Pendiente

* Portal del cliente para ver y responder sus tickets.
* Alta de tickets desde mensajes de WhatsApp entrantes.
* Encuesta de satisfacción al cerrar.
* QA funcional con un equipo real (alias de correo con el servidor de correo entrante configurado).
