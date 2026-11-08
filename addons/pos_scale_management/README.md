# Administración de balanzas para Odoo 20 CE

Addon `pos_scale_management` para administrar balanzas por empresa y sucursal, usando `stock.warehouse` como sucursal y los productos, impuestos, unidades y listas de precios existentes. No crea un segundo maestro de productos ni una entidad paralela de sucursales.

## Incluido en esta entrega

- Modelos de balanza, perfil de exportación, perfil de etiqueta, asignaciones de productos/categorías, excepciones de precio e historial de exportación.
- Menú **Balanzas**, tarjetas y listado, fichas con pestañas de productos, precios, etiquetas, exportación e historial.
- Roles de administrador, responsable de sucursal, operador y auditor. Los alcances por empresa y sucursal se aplican en backend usando el nuevo modelo `ir.access` de Odoo 20.
- Resolución de catálogo: productos activos, vendibles y habilitados para POS; las exclusiones explícitas prevalecen.
- Resolución de precio: excepción vigente por balanza → lista de precios de balanza/sucursal → precio estándar. La previsualización conserva precio, moneda, origen e impuestos calculados por Odoo.
- Validación de PLU requerido, duplicados y longitud.
- Previsualización con snapshot JSON, advertencias y errores.
- Interfaz de adaptadores, exportación individual y lote ZIP por sucursal con `manifest.json`; el lote aborta completo ante errores. Descargas autenticadas y hash SHA-256, con estado de descarga separado del estado de importación informado manualmente.
- Perfiles de códigos de barras configurables por longitud, prefijo, posiciones, peso/importe, decimales y dígito EAN-13. El POS intercepta etiquetas que coinciden con el perfil de la sucursal, resuelve PLU y agrega producto con peso o importe leído; las etiquetas comunes siguen usando el escáner nativo. PLU duplicados entre balanzas de una misma sucursal se rechazan como ambiguos.

## Compatibilidad Kretz/iTegra: pendiente de evidencia

El perfil Kretz/iTegra se instala en estado **Borrador**. La generación queda bloqueada; no se inventa extensión ni formato. El registro de auditoría muestra los datos que se exportarían y por qué está bloqueado.

Para habilitar el adaptador hacen falta un archivo real aceptado por iTegra, el modelo de balanza y las versiones utilizadas, además de una importación real exitosa. También se necesitan etiquetas impresas con sus códigos para configurar y verificar el lector de peso/importe. Hasta entonces no se declara compatibilidad productiva.

## Intercambio genérico DOLAN

Se incluye `CSV genérico DOLAN v1` para exportar un archivo UTF-8 con BOM, separador `;` y columnas PLU, código de barras, descripción, precio y moneda. Sirve como formato de intercambio; no afirma compatibilidad con un fabricante o software de balanza en particular. El perfil solo puede marcarse validado después de adjuntar evidencia de una importación aceptada por el software destino.

## Pendiente del PRD

- Implementar el serializador Kretz/iTegra y superar AC-06, AC-12 y AC-13 con evidencia real.
- Probar el perfil de etiquetas en navegador/lector real y pasar regresión con códigos normales (AC-10 y AC-11). La integración requiere asignar un perfil y PLU a la balanza/sucursal.
- Probar el flujo completo en navegador Windows y Android y revisar permisos con usuarios reales (AC-08, AC-09 y AC-16).
- Agregar el panel de indicadores y ampliar la batería para impuestos, vigencias de listas, redondeos, variantes y permisos multiempresa.
- Manual operativo con capturas y documento de compatibilidad por versión.

No se implementa comunicación directa con balanzas, servicio residente, gateway, IoT Box, APK ni automatización de iTegra.
