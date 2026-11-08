# Cierre de frentes POS — 2026-11-08

## Cambios aplicados

- **Descuentos por medio de pago:** el POS calcula la promoción para el medio seleccionado; el backend reserva presupuesto antes del cobro y verifica el medio registrado en la orden al sincronizarla. Una promoción de este tipo exige un solo medio de pago. Esto no afirma que Clover o Mercado Pago hayan liquidado el pago: falta enlazar el estado final e idempotente del adquirente.
- **Balanzas:** se añadió el formato de intercambio `CSV genérico DOLAN v1` (UTF-8 BOM, `;`, PLU, código de barras, descripción, precio y moneda). El perfil Kretz/iTegra continúa bloqueado y no se puede marcar validado sin evidencia; no se inventó su dialecto.
- **Cortes de red:** las autorizaciones nuevas/renovaciones necesitan servidor. El POS muestra aviso al perder conectividad y detiene acciones que requieren autorización. Las órdenes sin descuentos DOLAN conservan el modo offline estándar de Odoo. Los intentos de cobro Clover y QR quedan persistidos e idempotentes; el estado incierto bloquea otro cobro hasta obtener un resultado o conciliación supervisada.
- **Aprobación de beneficios:** el DNI puede generar una solicitud pendiente. Un supervisor distinto puede aprobar o rechazarla desde **Punto de Venta → Promociones DOLAN → Beneficios pendientes de aprobación**. El cajero vuelve a ingresar el DNI en la misma orden; la decisión queda en auditoría.
- **Diálogo de errores:** se parcheó la copia de diagnósticos para usar Clipboard API cuando exista y un fallback compatible con HTTP local. El error que abrió el diálogo es distinto del error secundario `navigator.clipboard.writeText`; este cambio evita que el botón de copiar oculte el primero, pero por sí solo no diagnostica el fallo de carga inicial de cada instalación.

## Validación ejecutada

- Instalación/actualización de `DOLAN_theme`, `DOLAN_discount_engine`, `DOLAN_pos` y `pos_scale_management` en una base QA temporal separada, con la imagen Odoo local; la base de trabajo no se usó.
- Suites etiquetadas de descuentos y balanzas ejecutadas previamente; los 4 casos POS existentes (`DOLAN_pos`) finalizaron con 0 fallos y 0 errores en Odoo 20.
- Para el cambio del cierre: `node --check`, `python -m compileall` y `git diff --check` sin errores. La prueba física de impresora y el cierre real se reservan para aceptación manual; no se cerró ninguna caja.
- `compileall`, `node --check`, parseo XML, unicidad de IDs de ACL y `git diff --check`: correctos.
- No se enviaron cobros, no se emitieron comprobantes fiscales y no se conectó a una terminal ni balanza real.

## Pendientes para afirmar cierre productivo

1. **Clover/Mercado Pago:** completar la prueba de checkout con terminal y credenciales de sandbox, incluyendo aprobada, rechazada, timeout, reconexión, conciliación y recuperación sin doble cobro. El código ya usa idempotencia y consulta persistente; no se hizo un cobro real en esta revisión.
2. **Kretz/iTegra:** recibir un archivo de referencia aceptado, modelo/firmware e iTegra disponible; validar importar un archivo desde el software real. Hasta entonces solo se ofrece CSV genérico.
3. **Red interrumpida durante el cobro:** completar conciliación del proveedor para distinguir aprobado, rechazado y estado desconocido y permitir reintento sin doble cobro.
4. **Prueba visual final:** probar en una caja POS con usuario cajero y supervisor, en el navegador que se usará, aprobación/rechazo, cambio de red y cola offline de Odoo.
5. **Error inicial de la instalación demo:** al reaparecer, copiar el traceback original ya sin que falle el botón de portapapeles; atender la excepción de carga que precedió al diálogo.

El cierre de código y pruebas locales queda hecho para la aprobación de beneficios, el intercambio CSV y los resguardos de autorización offline. La integración real de adquirentes, el formato de balanza Kretz y la reconciliación ante corte requieren evidencia externa y siguen siendo gates antes de producción.

## Actualización de integración de cobros (código posterior)

- **Mercado Pago QR:** checkout vinculado a `POST /v1/orders` con clave de idempotencia estable, registro persistente del intento en Odoo y consulta del estado real antes de marcar pagado. Un intento pendiente/ incierto bloquea un segundo QR para el mismo pedido y medio.
- **Mercado Pago Point:** usa el proveedor de POS incluido en Odoo 20 CE; la configuración de la terminal y la validación real requieren credenciales de la cuenta.
- **Clover:** checkout de navegador con operación persistida en Odoo, validación de referencia e importe y conciliación supervisada ante resultado incierto. Una línea en estado desconocido no se libera para cobrar otra vez.
- **Límite de verificación:** se validaron sintaxis de Python/JavaScript/XML y cambios Git; en este entorno no está disponible el motor Docker para ejecutar las pruebas Odoo ni un terminal/Cuenta Mercado Pago para una prueba de pago. No se afirma una liquidación de prueba en este cierre.
- **Kretz/iTegra:** continúa bloqueado. La estructura del archivo de ejemplo no demuestra que iTegra lo acepte; hace falta una importación real en la versión utilizada para habilitar ese exportador.

## Cierre diario e impresión del cierre Z

En Odoo 20 CE el popup de cierre llama `printSaleDetailsReceipt({ download: true })` después de que el backend confirma el cierre. El plugin nativo intenta imprimir en las impresoras configuradas y, si no informa éxito, rasteriza el recibo y lo descarga como PNG. Ese PNG no es el único formato disponible: el propio POS también expone el informe PDF nativo `point_of_sale.sale_details_report`.

Se agregó a `DOLAN_pos` una extensión frontend localizada, sin editar archivos del núcleo: para el cierre, prueba primero la impresora de recibos predeterminada y las demás asignadas al POS; si no hay impresora o ningún driver confirma el trabajo, solicita el informe PDF nativo. Los demás usos del recibo diario conservan el comportamiento estándar. No se simula que una impresora haya aceptado el trabajo.

## Idioma del POS

- El cierre y los rótulos nativos revisados tienen traducciones en `point_of_sale/i18n/es_419.po` (por ejemplo, Conteo de efectivo, Cerrar caja registradora, Nota de cierre, Venta diaria y Diferencia). Para verlos, el usuario debe tener cargado español latinoamericano o español de Argentina en Odoo.
- Se corrigieron textos ingleses visibles en la pantalla propia de cocina/seguimiento y tres etiquetas de configuración de Mercado Pago.
- La auditoría cubrió los flujos y addons DOLAN mencionados abajo; no certifica que cada traducción de todos los addons de terceros esté completa. Conviene fijar `es_AR` en el usuario de caja y recorrer pantalla por pantalla durante la prueba de aceptación.

## Matriz de capacidades POS y brechas

| Área | Estado observado en el repositorio/runtime | Pendiente o criterio para producción |
|---|---|---|
| Apertura, ventas, devoluciones, control de efectivo y cierre | Flujo nativo de Odoo 20 CE; el cierre agrega el asiento desde `pos.session`. | Probar con caja real, diferencias autorizadas y cierre contable; esta corrección solo cambia la salida del informe posterior. |
| Informe de cierre / cierre Z | Recibo diario nativo con impresora asignada y alternativa al PDF nativo. | Confirmar tamaño de papel, encabezado, pie y totales con la impresora real; verificar visualmente el PDF de cierre. |
| Tienda, restaurante, mesas y preparación | Nativo más KDS y seguimiento de pedidos DOLAN. | Revisar en sitio impresión por estación, reimpresión, pedidos abiertos al cerrar y tratamiento de anulaciones. |
| Promociones y descuentos | Motor DOLAN auditable, beneficios por DNI y autorización independiente; hay pruebas automatizadas del backend. | Prueba funcional completa en caja con supervisor y reversas; todavía falta reconciliar el pago real ante timeout/corte de red. |
| Balanzas | Perfiles/exportación y lectura de código de etiqueta; CSV genérico implementado. | El adaptador Kretz/iTegra sigue bloqueado hasta recibir muestra/importación real aceptada; no declarar compatibilidad de marca. |
| Clover | Checkout de POS enlazado al terminal, operación persistente, validación de importe/referencia y conciliación de supervisor si queda incierta. | Probar aprobación y corte de red en el Clover físico. El diálogo de prueba de $10 no sustituye la prueba de venta POS. |
| Mercado Pago QR/Point | QR usa órdenes reales con clave idempotente y GET de estado; Point usa el proveedor mantenido de Odoo 20 CE. Se persiste y bloquea el QR incierto para impedir otro cargo en el mismo pedido/medio. | Configurar token/terminal, probar orden QR y cobro Point en sandbox y validar rechazo/timeout/reconexión. No hay prueba real de pago en esta revisión. |
| Impresión ePOS / ESC-POS | Configuración de impresoras y pruebas; salida por navegador o puente ESC/POS. | Verificar en hardware la impresión del recibo comercial, comandas por categoría y cierre Z; comprobar estados de papel, ya que TCP ESC/POS no confirma papel/tapa. |
| Capacidades Enterprise | La documentación Odoo 20 lista flujos base, hardware, preparación, autoservicio, precios y reportes; Community tiene esas capacidades base en este árbol. | No hay checkout de código Enterprise ni licencia Enterprise en este entorno para una comparación binaria módulo-por-módulo. El capítulo de preparación de Odoo documenta componentes etiquetados como Enterprise, SMS y WhatsApp; las pantallas DOLAN no prueban equivalencia completa con ellos. |

### Alcance de la comparación con Enterprise

La comparación verificable se limita a las funciones POS publicadas en la documentación 20.0 y a los módulos Community presentes en este repositorio. El POS base cubre ventas de tienda/restaurante, cierres, métodos de pago, hardware y estadísticas; ciertas capacidades auxiliares o conectores de Odoo pueden depender de módulos Enterprise, IoT o proveedores. No se inspeccionó código propietario de Enterprise, por lo que no se afirma paridad completa. Próximo paso recomendado: convertir la matriz en una lista de aceptación por dispositivo y por flujo, sin ejecutar un cobro productivo hasta disponer de sandbox o autorización expresa.
