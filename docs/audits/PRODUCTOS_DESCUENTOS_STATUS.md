# Estado del PRD: productos, promociones y descuentos

**Corte de implementación local:** 2026-11-05. **Estado:** addon implementado para el alcance descrito y probado en QA aislada; no desplegado.

| Requisito | Estado de código | Qué cubre / qué falta |
|---|---|---|
| RF-01 Campañas | Parcial alto | Compañía, POS/sucursal, fechas, zona horaria, días/horas, fechas excluidas, prioridad, presupuesto, límites, productos/categorías/exclusiones y segmentos de clientes; falta canal fuera del POS e historial de aprobadores/autoría más completo. |
| RF-02 Vigencia | Parcial alto | Cálculo de servidor por calendario local y reservas; faltan feriados nacionales precargados y política integral ante orden diferida. |
| RF-03 Medio de pago | Pendiente | El motor calcula prorrateo con pagos confirmados en pruebas unitarias, pero el administrador no puede publicar estas reglas hasta que Clover/MP entreguen una confirmación persistida y verificable. |
| RF-04 Beneficio empleado | Parcial implementado | Identificación por DNI normalizado, elegibilidad por compañía/caja/fecha/productos, bloqueo de compra propia por defecto, topes por compra, cupo diario/mensual reservado con lock, token temporal, revalidación antes del cobro, consumo al registrar orden y reversión vía devolución POS. Falta aprobación independiente y validación visual en una caja POS real. |
| RF-05 Motor de promociones | Parcial alto | Porcentaje, fijo por unidad, precio especial y segunda unidad; exclusividad/acumulación explícita, redondeo de moneda, tope por línea/orden y aplicación sobre impuestos nativos. Falta cubrir con casos fiscales de caja y peso. |
| RF-06 Descuento manual | Parcial alto | Motivo, límites POS, solicitud a supervisor diferente, aprobación ligada a la línea, vencimiento y uso único. Falta prueba de caja multiusuario y una vista inmediata de estado de solicitud en el POS. |
| RF-07 Auditoría y alertas | Parcial | Auditoría append-only de cambios, aplicaciones, aprobaciones y devoluciones; alertas de presupuesto. Falta detección de anomalías configurable y alerta externa. |
| RF-08 Ticket/cliente | Parcial | Desglose de ahorro de campaña y descuento manual en el POS/recibo. No hay customer display conectado ni análisis de sobrecobro en efectivo. |
| RF-09 Informes | Parcial | Lista, pivote y gráfico de aplicaciones netas; exportación nativa Odoo. Falta XLSX específico y comprobación de cifras completas por campaña, medio y empleado. |
| RF-10 Multiempresa | Implementado en código | ACL y reglas por compañía, campañas y reservas ligadas a sesión. Falta ejecutar matriz de usuarios/compañías en QA. |
| RF-11 Balanzas | Parcial | El motor aplica el descuento a cantidad y precio de línea sin cambiar el precio maestro/etiqueta. Falta conectar parser POS y probar peso, precio variable y redondeo real con el addon de balanzas. |
| RF-12 Clover/MP | Pendiente integración | La integración de terminal existente no es una confirmación server-side idempotente aceptable para aplicar promos de pago. No se habilitan reglas dependientes de adquirente ni se simulan estados. |
| RF-13 Offline | Parcial con cierre seguro | Si el navegador reporta desconexión, elimina promociones/descuentos manuales antes de abrir el pago, avisa y permite vender al precio normal. Falta manejar cortes de red no detectados por el navegador y sincronización/reconciliación completa. |

## Verificación automatizada actual

En `dolan_products_audit_20261105`, Odoo 20 actualizó `DOLAN_discount_engine` y `DOLAN_pos`, cargando modelos, ACL, vistas, cron y assets del POS. La suite de descuentos terminó con **0 fallos y 0 errores en 9 casos**, incluida elegibilidad por DNI, DNI mal formado, compra propia, reserva/renovación/liberación de cupo y límite diario. La suite de regresión DOLAN POS/Mercado Pago terminó con **0 fallos y 0 errores en 4 casos**. El JavaScript pasó `node --check` y los Python pasaron `compileall`.

Es prueba de instalación y lógica automatizada de servidor en QA. Los tests Mercado Pago incluidos por `DOLAN_pos` son simulados, no son autorización del adquirente. No prueba caja OWL interactiva, impresora, balanza ni terminal real. No se procesaron pagos reales ni comprobantes fiscales.

## Trabajo necesario para cerrar antes de producción

1. Hacer la prueba funcional final del beneficio por DNI en la caja POS, con una venta de prueba que no se facture fiscalmente, y verificar el recibo y el cupo consumido/revertido.
2. Definir confirmación server-side para Clover y Mercado Pago, incluyendo estado final, importe, idempotencia, rechazo, cancelación, reversa y webhook. Hasta entonces, no publicar descuentos por medio de pago.
3. Conectar el parser de balanzas a las líneas POS y validar con productos pesables reales.
4. Agregar casos de impuestos y redondeo argentinos, multiusuario, conflictos de presupuesto, aprobaciones, devolución parcial, exportación y performance.
5. Ejecutar instalación/actualización completa y suites en una base de QA limpia; hacer revisión funcional en caja con métodos de prueba, sin crear comprobantes fiscales ni cobrar dinero real.
6. Aprobar el release y el despliegue por separado; este cambio no incluye despliegue a `10.1.1.9` ni a localhost.

## Entregables y referencias

- [Arquitectura](../architecture/DOLAN_DISCOUNT_ENGINE.md)
- [Guía del cajero](../user/DESCUENTOS_OPERACION.md)
- [Guía de configuración](../admin/DESCUENTOS_CONFIGURACION.md)
- [Controles de seguridad](../security/DESCUENTOS_AUDITORIA.md)
- [Notas de release y rollback](../implementation/DOLAN_DISCOUNT_ENGINE_RELEASE.md)
