# Hoja de ruta

Esta hoja resume áreas de trabajo del proyecto. La disponibilidad final depende de la versión de Odoo, los módulos instalados y los servicios externos configurados en cada despliegue.

## Plataforma e instalación

- Instaladores interactivos para Linux y Windows con perfiles de módulos.
- Alta inicial de empresa, usuario y base de datos sin incluir credenciales en el repositorio.
- Mejoras continuas de actualización, respaldo, observabilidad y recuperación.

## Gestión empresarial

- Facturación electrónica argentina, notas de crédito/débito, impuestos y consultas de padrón.
- Contabilidad multiempresa, bancos, conciliación e informes.
- Ventas, contactos, CRM, inventario y punto de venta.
- WhatsApp, IA/OCR, tableros BI y cotizaciones en moneda extranjera como integraciones opcionales.

## Equipamiento de punto de venta

- Configuración de terminales de pago y selección de diarios de cobro.
- Impresión de tickets y comandas mediante impresoras de red compatibles.
- Administración de balanzas, productos y perfiles de etiquetas.
- Validación específica de cada fabricante antes de declarar un formato de exportación como compatible.

## Criterios de cierre

- Instalar y actualizar en una base limpia con las dependencias documentadas.
- Verificar permisos, separación multiempresa y flujos de error.
- Probar las integraciones con servicios y hardware reales en un entorno controlado.
- Mantener respaldos fuera del repositorio y usar secretos suministrados por variables de entorno.
