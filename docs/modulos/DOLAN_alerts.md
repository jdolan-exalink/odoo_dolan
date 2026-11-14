# Alertas (`DOLAN_alerts`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `account` y `mail`.

## Para qué sirve

Avisar a los responsables cuando algo cruza un umbral, sin tener que ir a mirarlo.

## Condiciones disponibles

| Condición | Umbral | Necesita |
|---|---|---|
| Deuda vencida de clientes mayor a | importe | — |
| Clientes con mora mayor a N días | días | — |
| Pagos a proveedores de los próximos 7 días mayores a | importe | — |
| Caja proyectada negativa en las próximas 4 semanas | — | Flujo de caja |
| Diferencias de caja esperando aprobación | — | Caja y Tesorería |
| Productos con margen bajo, más de | cantidad | Costos |
| Productos bajo el stock mínimo, más de | cantidad | Inventario (reglas de reposición) |

## Cómo funciona

Cada hora se revisan las reglas activas. Si una se dispara, se crea una actividad de advertencia a cada
responsable y, si se pidió, un correo; queda un aviso en el historial con valor, umbral y mensaje. No se repite
hasta que pase el tiempo de espera de la regla (por defecto 24 horas). *Revisar ahora* la evalúa en el momento.
Una regla que falla no frena a las demás (queda anotado en la regla).

## Permisos

Los usuarios ven las reglas de sus empresas y los avisos de las reglas donde son responsables. Los contadores
crean y editan reglas y ven todos los avisos.

## Pruebas automáticas

5 tests: deuda vencida con tiempo de espera, umbral no alcanzado, mora y pagos de la semana, condiciones que
necesitan otro módulo y tarea programada.

## Pendiente

* Aviso por WhatsApp.
* Resumen diario por correo con todas las alertas.
