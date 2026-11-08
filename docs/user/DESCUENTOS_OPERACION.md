# Operación de promociones y descuentos en caja

## Alcance actual

El addon aplica campañas publicadas y descuentos manuales en el Punto de Venta. Los descuentos automáticos se previsualizan en la línea, y el servidor vuelve a calcularlos y reserva presupuesto antes de abrir el cobro. El detalle de ahorro aparece en el ticket. La campaña debe estar activa para la compañía y caja correspondientes.

## Venta con promociones

1. Abrí una sesión POS conectada al servidor.
2. Cargá productos y cliente, si la campaña segmenta por cliente.
3. Revisá el nombre y el ahorro indicados en las líneas y el total.
4. Al tocar **Cobrar**, el servidor valida las reglas y reserva el presupuesto por un máximo de dos horas.
5. Si el POS advierte que una campaña agotó presupuesto, revisá el nuevo total antes de cobrar. La venta continúa a precio normal cuando vuelvas a presionar Cobrar.

No cambies manualmente el total de un pago que ya pudo haberse presentado a una terminal. Si la autorización venció o la orden cambió, volvé a la pantalla de venta y presioná Cobrar para recalcularla.

## Descuento manual

Ingresá el descuento desde los controles nativos del POS y describí el motivo cuando lo solicite. El límite depende de la configuración de esa caja y del rol del usuario. Si supera el límite, un supervisor distinto debe aprobarlo desde **Punto de Venta → Promociones DOLAN → Autorizaciones**. La aprobación se usa una vez y queda vinculada a esa línea y orden. El cajero debe volver a presionar Cobrar después de la aprobación.

## Devoluciones

Usá el flujo nativo de devolución POS y seleccioná la línea original. El addon revierte el descuento de manera proporcional y auditable. No edites ni elimines las aplicaciones de descuento.

## Beneficio de empleado por DNI

1. Con la venta abierta y sus productos cargados, tocá **Beneficio empleado**.
2. Ingresá el DNI. Si el beneficio corresponde a esta empresa/caja y los productos califican, el POS muestra el beneficio aplicado.
3. Revisá el descuento y el total antes de cobrar. El servidor vuelve a validar el beneficio y su cupo al iniciar el cobro.
4. Para quitarlo antes de cobrar, volvé a **Beneficio empleado** y confirmá con el campo vacío. Se libera la reserva.

Un DNI no elegible, un producto excluido, una caja no habilitada, una compra propia bloqueada o un cupo agotado impiden aplicar el beneficio. Se necesita conexión al servidor. Si el beneficio requiere aprobación, la solicitud queda en **Punto de Venta → Promociones DOLAN → Beneficios pendientes de aprobación**. Un supervisor distinto del cajero puede aprobarla o rechazarla con motivo; luego el cajero vuelve a ingresar el DNI en la misma orden. La solicitud y su decisión quedan auditadas.

## Sin conexión

No se crean ni renuevan autorizaciones de descuento sin conexión al servidor. Si hay un corte, el POS avisa y bloquea la autorización nueva; una orden sin descuentos DOLAN conserva el mecanismo offline estándar de Odoo. Si el adquirente pudo aceptar un cobro durante un corte, comprobá su estado antes de reintentar: la conciliación automática de un resultado incierto requiere integración del proveedor.

## Funciones aún no habilitadas

Las promociones por medio de pago están disponibles cuando se selecciona un único medio; el servidor reserva el descuento y al sincronizar comprueba que la orden use ese mismo medio. Esto no valida por sí solo la liquidación del adquirente. Falta cerrar la integración idempotente de estado, timeout, cancelación y reversa para Clover/Mercado Pago.
