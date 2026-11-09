# DOLAN Promociones y Control de Descuentos

Addon para Odoo 20 Community. Usa los productos, impuestos, listas de precios, pedidos, cobros y devoluciones nativos de Odoo; no crea un catálogo o un flujo de pagos paralelo.

## Funciones implementadas

- Campañas por compañía, POS/sucursal, prioridad, fechas, zona horaria, días, horarios, feriados/exclusiones, presupuesto total y tope por pedido.
- Reglas por producto, categoría, producto excluido, cliente/segmento, cantidad mínima, prioridad y compatibilidad. Beneficios porcentuales, importe fijo por unidad, precio especial y segunda unidad.
- Publicación versionada con snapshot y SHA-256. Una publicación activa es inmutable; pausar y volver a publicar genera una versión nueva.
- Previsualización en POS y autorización del servidor antes de entrar al cobro. El presupuesto se reserva de forma transaccional entre cajas; si no alcanza, no se reduce silenciosamente el importe después del pago.
- Descuentos manuales con motivo, límites por caja y solicitudes de autorización de un supervisor distinto del cajero; aprobaciones de un solo uso, ligadas a línea/orden y con vencimiento.
- Beneficio de empleado por DNI: normaliza el número, valida compañía/caja/vigencia/productos y compra propia, reserva cupo diario y mensual con bloqueo transaccional, revalida antes del pago y consume el beneficio al registrar la orden. El DNI no se copia a la orden ni al recibo.
- Aplicación inmutable por línea para campañas y descuentos manuales; detalle en POS/recibo, auditoría y reportes de lista, pivote y gráfico.
- Reversión proporcional al procesar devoluciones POS reales; libera proporcionalmente el presupuesto promocional.
- Simulador de campaña, panel de alertas y aislamiento de datos por compañía.

## Límites deliberados

- Las reglas por medio de pago se evalúan al seleccionar un medio en caja, antes de iniciar el cobro; la autorización y el presupuesto quedan reservados en servidor y la orden sincronizada debe llevar el mismo medio. Solo se admite un medio por orden cuando la promoción depende de él. Esto verifica el medio registrado por Odoo; no equivale a una confirmación independiente de liquidación de Clover/Mercado Pago.
- El beneficio por DNI admite aprobación o rechazo de un supervisor distinto del cajero, con vencimiento y auditoría. El cajero debe volver a identificar al beneficiario en la misma orden después de la aprobación para aplicar el descuento. Se pueden usar partners como beneficiarios; no requiere instalar Empleados/HR.
- Una reserva de beneficio/campaña necesita conexión para crearse o renovarse. Al perder la conexión, el POS advierte y bloquea nuevas autorizaciones; la cola offline estándar de Odoo queda a cargo de la sincronización. Un corte durante la autorización del adquirente no puede conciliarse solo con `navigator.onLine`: antes de producción hay que integrar estado idempotente y reconciliación del proveedor.
- No se genera un XLSX propio. Los reportes se apoyan en exportación nativa de lista y pivote de Odoo.
- La auditoría registra denegaciones como solicitudes/errores visibles; un intento rechazado por una excepción que revierte toda la transacción no puede dejar un asiento en esa misma transacción.

## Roles y operación

1. Asignar a cada responsable comercial el grupo **Administrador comercial de promociones**.
2. Asignar **Supervisor de descuentos** a quienes pueden aprobar excepciones; nunca usar la misma cuenta que solicitó el descuento.
3. Asignar **Cajero con descuentos** y el grupo nativo de usuario POS al equipo de caja.
4. Configurar límites de descuento manual en cada POS. Cero bloquea el descuento manual del cajero.
5. Crear campaña, reglas y exclusiones desde **Punto de Venta → Promociones**. Publicar solo después de revisar alcance, vigencia y topes.
6. Para el beneficio de empleado, crear el beneficio desde **Punto de Venta → Promociones → Beneficios de empleados**, seleccionar empresa, partner, DNI, productos y límites. El DNI se consulta en caja y solo es legible para administradores comerciales.
7. En caja, el POS valida la promoción o el DNI en el servidor antes de entrar al cobro. Para descuento manual solicita el motivo; si excede el límite, un supervisor lo aprueba desde **Autorizaciones** y el cajero vuelve a presionar Cobrar.
8. Para revertir un descuento, registrar una devolución POS real con la línea original. No editar la aplicación promocional a mano.

## QA y release

Las pruebas automatizadas usan datos de prueba y no crean comprobantes fiscales ni cobros reales. Se instalaron los módulos en una DB temporal y se ejecutó la suite de descuentos/balanzas en QA local. Sigue pendiente prueba interactiva POS con una caja y un instrumento de prueba; el estado real del cobro y la reconciliación ante cortes dependen de la integración del adquirente.

Guías: [operación de caja](../../docs/user/DESCUENTOS_OPERACION.md), [configuración](../../docs/admin/DESCUENTOS_CONFIGURACION.md), [seguridad y auditoría](../../docs/security/DESCUENTOS_AUDITORIA.md), [estado frente al PRD](../../docs/audits/PRODUCTOS_DESCUENTOS_STATUS.md) y [release/rollback](../../docs/implementation/DOLAN_DISCOUNT_ENGINE_RELEASE.md).
