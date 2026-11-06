# Configuración de promociones y descuentos

## Roles

- **Administrador comercial de promociones:** crea reglas, configura campañas, publica, pausa y archiva dentro de las compañías autorizadas.
- **Supervisor de descuentos:** puede aprobar descuentos excepcionales solicitados por otra cuenta y resolver alertas.
- **Cajero con descuentos:** puede aplicar el descuento manual dentro del límite de su POS y crear solicitudes de aprobación.
- **Auditoría:** acceso de lectura a eventos y aplicaciones según las compañías permitidas.

Separá las cuentas de cajero y supervisor. No otorgues el rol de administrador comercial a usuarios de caja por conveniencia.

## Crear una campaña

1. Abrí **Punto de Venta → Promociones DOLAN → Campañas** y creá un borrador.
2. Elegí compañía, cajas/sucursales, rango de vigencia, zona IANA, días, horas y fechas excluidas.
3. Añadí reglas por producto/categoría, exclusiones, cliente/segmento, cantidad mínima, prioridad, compatibilidad y beneficio.
4. Definí presupuesto y máximo por operación. Cero indica sin límite monetario.
5. Ejecutá el simulador con una fecha, caja y productos representativos.
6. Publicá. La publicación genera una versión inmutable con snapshot y hash. Para cambiar condiciones, pausá, editá y publicá una nueva versión.

La fecha final es exclusiva en el calendario local de la campaña. El descuento no modifica el precio de lista, precio de balanza ni impuesto del producto; se calcula sobre la línea POS y Odoo recalcula sus impuestos nativos.

## Descuentos manuales

En **Punto de Venta → Configuración**, definí los límites de cajero y supervisor por cada POS. Un límite cero bloquea el descuento manual. Configurá aprobación para excesos y asigná supervisores que no compartan sesión con el solicitante.

## Control diario

Revisá **Aplicaciones**, **Auditoría**, **Autorizaciones** y **Alertas** por compañía. Cerrá alertas con una resolución breve. Las reservas expiran a las dos horas; el cron limpia reservas y aprobaciones vencidas. Las aplicaciones, sus versiones y reversiones no se pueden editar desde formularios.

## Beneficios de empleados por DNI

1. En **Punto de Venta → Promociones DOLAN → Beneficios de empleados**, elegí empresa y partner beneficiario e ingresá su DNI. Se normalizan separadores y se aceptan entre 6 y 10 dígitos.
2. Indicá vigencia, cajas habilitadas, productos/categorías permitidos y productos excluidos.
3. Configurá tipo e importe del beneficio, máximo por compra y cupos diarios/mensuales. Un tope en cero significa sin límite.
4. No actives **Requiere aprobación**: la aprobación de beneficios aún no está habilitada y la configuración será rechazada.
5. El cajero ingresa el DNI desde **Beneficio empleado** en una venta conectada. El servidor reserva cupo antes del pago y lo consume al sincronizar la orden. Si se cancela la operación, se puede quitar el beneficio para liberar la reserva; las reservas vencen a las dos horas.

El DNI y el mapeo de beneficiario son visibles solo para el administrador comercial. El POS recibe una autorización temporal, no el DNI. Se puede usar un partner como ficha de beneficiario; no hace falta instalar el módulo Empleados.

## Limitaciones para configurar

- Las campañas por medio de pago no se publican hasta tener estado final, importe y referencia idempotente verificados en el servidor.
- Beneficios por DNI están conectados al POS y validados automáticamente en backend; falta probar el flujo visual en la caja destino y completar aprobación independiente.
- No activar para venta real hasta validar los casos fiscales de Argentina, balanza, permisos multiempresa y ticket en la base y los dispositivos destino.
