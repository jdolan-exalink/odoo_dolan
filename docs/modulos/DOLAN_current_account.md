# Cuentas corrientes (`DOLAN_current_account`)

Carpeta del Inicio: **Facturación y Finanzas**. Estado: beta. Depende de `account` y `mail`.
Capacidad del PRD: F06 (Centro de Cuentas Corrientes, sección 5).

## Para qué sirve

Una sola pantalla para ver cuánto debe cada cliente y cuánto se le debe a cada proveedor, por empresa, con lo
vencido y su antigüedad, las promesas de pago y el estado de cuenta a cualquier fecha.

## De dónde salen los saldos

No hay saldos guardados aparte: la vista `dolan.current.account` se calcula en el momento desde los apuntes
publicados de las cuentas a cobrar y a pagar (`account.move.line`), usando el **residual**. Por eso coincide
siempre con la contabilidad y con lo conciliado: facturas, notas de crédito, pagos parciales y anticipos se
reflejan solos. Los anticipos y créditos sin imputar aparecen en *Anticipos y créditos sin aplicar*. Los importes
de proveedores se muestran en positivo.

## Cómo se usa

* **Saldos**: lista por contacto y empresa con saldo, vencido, a vencer, antigüedad (1-30, 31-60, 61-90, más de
  90 días), días de mora y prometido. Filtros: clientes, proveedores, con vencido, más de 90 días, con promesa,
  saldo a favor. Desde cada fila: comprobantes abiertos, movimientos, promesa de pago y estado de cuenta.
* En la ficha del contacto hay dos botones nuevos: *Cuenta corriente* y *Estado de cuenta*.
* **Promesas de pago**: importe, fecha y canal del contacto. Cada hora se revisan: pasan a *Cumplida* cuando
  entran cobros por ese importe desde que se registró, o a *Incumplida* si vence la fecha sin cobros.
* **Estado de cuenta**: contacto, cuenta (cliente o proveedor), desde y fecha de corte. Saldo inicial,
  movimientos con saldo acumulado y saldo a la fecha de corte. Sale en **PDF**, **Excel** o **por correo** al
  contacto (con el PDF adjunto). Opción de mostrar solo los comprobantes abiertos a la fecha de corte.

## Permisos

Usuarios de Facturación (`account.group_account_invoice`): ven saldos y estados de cuenta y registran promesas.
Los contadores pueden borrar promesas. Todo filtrado por las empresas del usuario.

## Pruebas automáticas

6 tests: saldos y antigüedad con anticipo, conciliación sin duplicar, proveedor en positivo, estado de cuenta igual
al mayor a la fecha de corte (y PDF y Excel), promesas cumplidas e incumplidas, aislamiento entre empresas.

## Pendiente

* Cobranza activa por WhatsApp desde la cuenta corriente (estado de cuenta, aviso de vencimiento, reclamo) con
  plantillas por empresa, franja horaria, exclusiones, opt-out, límite de frecuencia y aprobación de envíos
  masivos (PRD 5.3). Hoy existe el envío manual de DOLAN WhatsApp y el envío por correo.
* Bloqueo de venta desde la ficha usando el límite de crédito de `DOLAN_credit_limit`.
* Multimoneda: hoy los importes se muestran en la moneda de la empresa (los residuales en moneda extranjera
  quedan valorizados en pesos).
* Filtro por sucursal cuando exista el módulo de Sucursales.
* Cobro desde el POS idempotente y auditado (PRD 5.5 punto 6): queda en el módulo de Caja.
