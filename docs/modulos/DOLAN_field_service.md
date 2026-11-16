# Órdenes de servicio (`DOLAN_field_service`)

Carpeta del Inicio: **Servicios**. Estado: beta. Depende de `mail` y `account`. Perfiles: Servicios y Completo.

## Para qué sirve

Trabajos en el domicilio del cliente: pedido, técnico, fecha, horas, materiales, conformidad firmada y factura.

## Cómo se usa

1. El responsable crea la orden con cliente, dirección del trabajo, pedido y técnico, y la **programa**
   (exige técnico y fecha). Vista calendario por técnico.
2. El técnico la **empieza**, carga horas (pestaña Trabajo), materiales y el trabajo realizado, y toma la
   **conformidad**: nombre y firma del cliente.
3. **Terminar** exige trabajo realizado y, si la orden lo pide (por defecto sí), la firma.
4. El responsable **crea la factura**: borrador al cliente con los materiales y una línea de mano de obra por las
   horas (producto «Mano de obra (hora)» con su precio, editable por orden). La factura sigue el circuito normal
   de Facturación ARCA. La orden queda *Facturada* y bloqueada.

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.service.order` | Orden `OS-año-#####`, estados, técnico, fechas, importes, firma, factura. |
| `dolan.service.order.line` | Materiales usados. |
| `dolan.service.order.time` | Horas por técnico y día. |

## Permisos

* **Técnico**: ve y trabaja solo las órdenes asignadas a él (no las crea ni borra).
* **Responsable**: todas las órdenes de sus empresas; programa y factura.

## Pruebas automáticas

5 tests: importes, requisitos para terminar, programar sin técnico, factura y bloqueo, visibilidad del técnico.

## Pendiente

* App móvil del técnico con trabajo sin conexión.
* Descontar materiales del stock (depósito de la camioneta).
* Generar la orden desde un ticket de Mesa de ayuda o desde un Contrato.
