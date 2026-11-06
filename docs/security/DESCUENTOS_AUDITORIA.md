# Seguridad y auditoría del motor de descuentos

## Límites de confianza

El navegador solo muestra una previsualización. El servidor valida sesión POS, usuario, compañía, producto, cantidad, precio, campaña y reglas. Antes del pago crea una reserva con UUID de orden y propuestas autoritativas. Al sincronizar la orden compara las líneas/descuentos con esa reserva; no reemplaza ni reduce el total luego de un posible cobro electrónico.

Las llamadas POS requieren sesión abierta asignada al usuario autenticado. Las reservas están ligadas a esa sesión. La publicación requiere grupo comercial; aprobaciones requieren un usuario distinto del solicitante. Una autorización se limita a una línea/orden, caduca y se consume una sola vez.

El endpoint de beneficio recibe el DNI solo para buscar el beneficio activo en la compañía de la sesión. Revalida usuario/sesión, caja, vigencia, productos, compra propia y límites. La tabla de reserva guarda partner, empresa, caja/orden, token opaco, propuestas, importe y vencimiento; no almacena el DNI. Solo el administrador comercial puede leer/configurar el DNI y el mapeo del beneficiario. Los claims no tienen permisos de escritura en la interfaz; sus cambios se hacen mediante métodos del servidor que validan la sesión POS.

## Datos registrados

El módulo registra actor, compañía, caja/orden/línea, campaña y versión, importes, razón y aprobación cuando aplica. Las aplicaciones, snapshots publicados, reversiones y eventos de auditoría son append-only desde el acceso ordinario. Los datos de empleado se mantienen fuera del ticket.

No se almacena PIN de pago ni datos de tarjeta. El DNI sí forma parte de la ficha administrativa del beneficio, con acceso limitado; se mantiene fuera del pedido POS y del ticket.

## Separación por compañía

Las ACL se asignan por función y las reglas de acceso filtran por compañías habilitadas. Las reservas se limitan a la sesión propia. En ambientes multiempresa, validar con usuarios reales no administradores: consultar, crear campañas, solicitar aprobación, aprobar desde otra cuenta, leer reportes y acceder a RPC directamente.

## Eventos y limitaciones

Se conservan altas/cambios/publicaciones/pausas de campaña, aplicación y reversión, solicitudes/aprobaciones y agotamiento de presupuesto. Una excepción que provoca rollback de toda la transacción no puede persistir una auditoría en esa misma transacción; por eso se usan alertas/respuestas controladas para denegaciones que deben quedar registradas. Completar detector configurable de anomalías y retención/exportación antes de usar el addon como control antifraude integral.

Odoo administra el acceso a la base y el respaldo de registros. El addon no firma criptográficamente la tabla de auditoría ni protege frente al superusuario de base de datos. Limitar ese acceso y conservar backups inmutables conforme a la política de la empresa.
