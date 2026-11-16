# Agenda de turnos (`DOLAN_appointment`)

Carpeta del Inicio: **Servicios**. Estado: beta. Depende de `mail` y `resource`. Perfiles: Servicios y Completo.

## Para qué sirve

Dar turnos a clientes con un profesional o un recurso (sala, box, equipo) sin superposiciones y dentro del
horario de atención, con recordatorio automático.

## Cómo se usa

1. **Configuración → Profesionales y recursos**: nombre, tipo, usuario (si es una persona del sistema), horario
   de atención, zona horaria y servicios que atiende.
2. **Configuración → Servicios**: duración, intervalo entre turnos ofrecidos, indicaciones para el cliente y
   recordatorio (horas de anticipación, por correo y/o WhatsApp).
3. **Agenda**: vista calendario por profesional. Estados: *Reservado → Confirmado → Atendido*, o *Ausente* /
   *Cancelado* (se puede volver a reservar).

Controles: no deja dos turnos del mismo profesional superpuestos, ni turnos fuera de su horario o en sus
ausencias, ni un servicio que el profesional no atiende. Cancelar libera el horario.

Recordatorios: cada 15 minutos se envían los que corresponden (una sola vez por turno). El de WhatsApp usa la
cuenta de DOLAN WhatsApp de la empresa; si falla, queda anotado en el turno y no frena a los demás.

`dolan.appointment.type._free_slots(recurso, día)` devuelve los horarios libres de un día; es la base para
reservar desde el portal.

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.appointment` | Turno `TU-año-#####`: cliente, servicio, profesional, inicio, fin, estado, recordatorio enviado. |
| `dolan.appointment.type` | Servicio: duración, intervalo, recordatorios. |
| `dolan.appointment.resource` | Profesional o recurso: horario, zona horaria, servicios. |

## Permisos

* **Recepción**: da, mueve y cancela turnos; ve servicios y profesionales.
* **Responsable**: además configura servicios y profesionales y borra turnos.
* Filtrado por empresa.

## Pruebas automáticas

9 tests: numeración y fin del turno, superposición, cancelado libera, fuera de horario, servicio no atendido,
horarios libres, estados, recordatorio único y permisos.

## Pendiente

* Reserva desde el portal o un link público.
* Seña con Mercado Pago.
* Facturar el turno atendido.
* Confirmación del cliente respondiendo el WhatsApp.
