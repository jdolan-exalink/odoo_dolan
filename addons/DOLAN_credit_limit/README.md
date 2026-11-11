# DOLAN Límite de crédito con bloqueo

Extiende el límite de crédito nativo de Odoo (Contabilidad > Ajustes > Límite de crédito de ventas), que por sí solo sólo avisa.

- **Modo por empresa**: sólo avisar o bloquear la confirmación del pedido de venta (Ajustes, debajo del límite por defecto).
- **Riesgo del cliente**: saldo de cuenta corriente + pedidos confirmados sin facturar + cheques de terceros en cartera que todavía no vencieron (se puede desactivar).
- **Bloqueo manual** del crédito de un cliente en la pestaña Facturación del contacto.
- **Excepciones**: el grupo *Autorizar ventas sobre el límite de crédito* puede confirmar igual; queda registrado en el pedido y en el chatter.
- **Punto de Venta** (`DOLAN_credit_limit_pos`, se instala solo si hay POS): antes de validar una venta con cobro en cuenta corriente consulta el límite. Un usuario autorizado ve la opción de autorizar; el resto ve el motivo. Sin conexión no se bloquea la caja.
