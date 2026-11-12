# Changelog — Suite DOLAN para Odoo CE 20

Todas las novedades relevantes del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado de cada módulo respeta el esquema de Odoo `20.0.MAJOR.MINOR.PATCH`.

## [Unreleased]

### Agregado
- Suite **Personal**, ola 1 (ver `docs/DOLAN_PERSONAL_SUITE.md`):
  - `DOLAN_hr_core 20.0.1.0.0` (nuevo): legajo único con CUIL validado, número de legajo y fecha de ingreso reconocida, únicos por compañía entre empleados activos; antigüedad y días de vacaciones del art. 150 LCT; establecimientos y centro de costos con vigencia en las versiones estándar del empleado (`hr.version`); grupo **Supervisor de Personal**; asistente **Vincular empleado** en Usuarios, que propone fichas existentes sin usuario (por correo, CUIL o nombre) antes de crear una nueva y reemplaza al botón estándar "Crear empleado".
  - `DOLAN_personal_operativo` y `DOLAN_personal` (nuevos, paquetes): Personal Operativo instala legajos, Ausencias y Asistencias sin Sueldos; Personal Completo suma Sueldos y Jornales. El perfil Completo del instalador instala Personal Completo.
  - `DOLAN_theme 20.0.2.79.0`: carpeta **Personal** en el Inicio con Empleados, Ausencias, Asistencias, Sueldos y Reclutamiento (solo las instaladas y que el usuario puede abrir). Los escritorios nuevos la traen; los ya armados la agregan con "Agregar carpeta Personal" en Configuración de pantalla, sin tocar el resto.
- Suite **Personal**, olas 2 a 7 (todas `20.0.1.0.0`, nuevas):
  - `DOLAN_hr_leave`: licencias de la LCT como tipos de ausencia editables con tope por evento y por año y código de novedad; asignación anual de vacaciones por antigüedad (art. 150) y proporcional (art. 153) sin duplicar años; vigencia y arrastre por compañía; aviso de cobertura por sector.
  - `DOLAN_hr_scheduling` (app **Turnos**): turnos con pausa, cruce de medianoche y horas nocturnas; plantillas con ciclos 4x2, 6x2, 7x7 o libres; cuadrillas con dotación mínima; cronogramas que generan turnos en UTC según la zona del empleado, saltean licencias aprobadas, controlan superposición y descanso, se publican y se versionan con motivo.
  - `DOLAN_hr_attendance`: relojes (CSV, API o manual) con desfase y zona horaria; eventos crudos inmutables e idempotentes; armado de asistencias estándar con faltas de entrada o salida marcadas; conciliación contra el turno con tolerancia por turno, sector o compañía; incidencias (tarde, salida anticipada, ausencia, exceso, trabajo sin turno) con justificación y aprobación; correcciones con motivo que conservan el valor original y requieren un aprobador distinto del solicitante. Menú Turnos > Presentismo.
  - `DOLAN_hr_overtime`: horas extra al 50 % y al 100 % (sábado desde la hora de corte, domingo y feriados) desde los excesos conciliados; autorización previa o posterior con nota, tope diario y avisos mensual y anual; períodos de novedades con recolección, cierre, reapertura y exportación CSV; rectificación por diferencia de un período cerrado. Menú Turnos > Novedades.
  - `DOLAN_hr_payroll_bridge` (se instala solo con Sueldos): pasa novedades cerradas a los recibos según una tabla de equivalencias, una sola vez, con simulación por liquidación y liberación mientras el recibo no esté confirmado.
  - `DOLAN_hr_portal`: **Mi legajo** en el portal (/my/personal) con turnos, saldos, pedido de licencia, justificación de incidencias, pedido de corrección de fichada y cambio de turno entre compañeros. `DOLAN_hr_portal_payroll` (se instala solo con Sueldos) suma los recibos confirmados, su PDF y la firma.
  - `DOLAN_hr_reports` (app **Reportes de Personal**): tablero con ausentismo, incidencias, horas extra, novedades y documentos, cada número abre los registros de origen; supervisores ven solo su equipo.
  - `DOLAN_hr_documents`: legajo digital con tipos (vencimiento, aviso, obligatorio, confidencial, visible para el empleado), huella SHA-256, conformidad del empleado ligada a la huella y aviso de vencimientos.
  - `DOLAN_hr_talent` (app **Gestión RRHH**): cursos con vigencia que otorgan la habilidad certificada al cerrar la sesión, puestos con capacitación obligatoria, ciclos de evaluación con objetivos ponderados, nota privada de RRHH y conformidad del empleado; selección sobre Reclutamiento estándar.
  - Los paquetes Operativo y Completo incluyen los módulos nuevos.

### Seguridad
- `DOLAN_payroll_ar 20.0.1.2.0`: un recibo confirmado ya no vuelve a borrador ni se edita (conceptos, novedades, fechas, importes); se corrige con **Rectificar**, que lo anula conservando huella y motivo y crea un borrador que lo reemplaza. Un recibo con huella no se puede borrar.
- `DOLAN_payroll_ar 20.0.1.1.0`: Sueldos tiene permisos propios (**Liquidación de sueldos** y **Responsable de sueldos**) en lugar de los de Empleados; un Oficial de Empleados ya no ve básicos, escalas, recibos ni liquidaciones. Al actualizar, los Oficiales y Administradores de Empleados existentes reciben el grupo equivalente para no perder acceso. CUIL, legajo y fecha de ingreso pasan a `DOLAN_hr_core` con el mismo nombre de campo, sin migrar datos.

### Seguridad y distribución
- `DOLAN_ocr`: reemplaza PyMuPDF por `pypdfium2==5.10.1` para renderizar PDFs y decodificar QR; serializa llamadas al motor PDFium y crea PDFs de prueba con ReportLab. Los Dockerfiles Linux, actualización y Windows fijan la misma versión y copian notices del wheel a `/opt/dolan/licenses/pypdfium2`.
- CI y `scripts/validate_addons.py` ahora enumeran los 18 addons versionados del repositorio, incluidos descuentos, terminales, ePOS y balanzas.
- Añadidos auditoría, arquitectura objetivo, roadmap P0–P3 y matriz inicial de notices en `docs/DOLAN_DISTRIBUTION_*.md` y `docs/THIRD_PARTY_NOTICES.md`.

### Agregado
- `DOLAN_ai 20.0.1.36.0`: asistente **Nueva conexión** (IA > Configuración > Nueva conexión, o desde el chat cuando no hay conexión lista). Se elige el proveedor (OpenRouter, ChatGPT, OpenAI API u Ollama), se pega la clave o se vincula la cuenta, se elige el modelo de la lista real del proveedor y se prueba con una respuesta corta. En OpenRouter valida la clave y muestra el saldo sin gastar créditos, y marca y propone los modelos gratis si la cuenta no tiene saldo. La conexión terminada queda como la única activa de la compañía (botón "Usar esta conexión" en Conexiones de IA). El selector de modelos lee el catálogo de OpenAI API y Ollama (antes mostraba siempre modelos de OpenAI) y los proveedores por API key figuran como conectados cuando tienen la clave. Los pedidos a OpenRouter piden como máximo 4096 tokens de respuesta, para que una cuenta con poco saldo no reciba HTTP 402.
- `DOLAN_ai 20.0.1.35.0`: proveedor **OpenRouter** por API key (modo "OpenRouter" en IA > Configuración > Proveedores). Completa endpoint y modelo (`openrouter/auto`), lista en el chat solo modelos que admiten herramientas, reintenta sin herramientas si el modelo no las soporta, explica la falta de créditos (HTTP 402) y los errores del proveedor de origen, y agrega un botón "Probar conexión" para los proveedores por API key.
- `DOLAN_account_reports 20.0.1.0.0` (nuevo): estado de situación patrimonial, estado de resultados y sumas y saldos interactivos (Contabilidad > Reportes > Informes interactivos) con despliegue de apuntes, hasta tres períodos de comparación con variación, notas por cuenta, exportación a Excel e impresión. Tablero *Finanzas DOLAN* en la planilla de Community con resultados mensuales y situación patrimonial.
- `DOLAN_views 20.0.1.3.0`: tipos de vista genéricos Gantt (`dolan_gantt`, con arrastre para mover fechas), Mapa (`dolan_map`, OpenStreetMap), Grilla (`dolan_grid`, editable) y Cohorte (`dolan_cohort`) que sirven para cualquier modelo con el buscador estándar. Se suman solos a Tareas, Partes de horas, Fabricación, Contratos de flota, Alquileres, Suscripciones, Contactos, CRM y Ventas cuando están instalados, y se quitan al desinstalar.
- `DOLAN_marketplace 20.0.1.0.0` (nuevo): conector de Mercado Libre (OAuth) y Tiendanube. Lee las publicaciones y las vincula a productos por SKU, envía stock libre del depósito y precio de la lista elegida, baja ventas pagadas como pedidos confirmados con alta del comprador (Consumidor Final si no hay CUIT) y puede facturarlas solas. Notificaciones `orders_v2` de Mercado Libre, webhooks firmados de Tiendanube y tareas programadas de respaldo; cada operación queda en un registro.
- `DOLAN_credit_limit 20.0.1.0.0` y `DOLAN_credit_limit_pos 20.0.1.0.0` (nuevos): el límite de crédito nativo pasa de aviso a bloqueo configurable por empresa. El riesgo suma saldo, pedidos sin facturar y cheques de terceros en cartera no vencidos; se puede bloquear el crédito de un cliente a mano y un grupo autoriza excepciones (quedan en el pedido). El POS consulta el límite antes de validar una venta en cuenta corriente.
- `DOLAN_pricelist 20.0.1.0.0` (nuevo): actualización masiva de precios por porcentaje, monto o margen sobre el costo, filtrada por categoría, proveedor o productos, con vista previa editable, redondeo y reversión del lote. Actualiza precio de venta, costo o precios fijos de una lista. Precios atados al dólar recalculados con la cotización del día (acción y cron) e historial de precios por producto.
- `DOLAN_ai 20.0.1.34.0`: dictado Whisper con servicio local `faster-whisper` en Docker, endpoint interno compatible con multipart, modelo CPU `small`/`int8` y alternativa opcional OpenAI API. El audio queda dentro de la red local.

### Corregido
- `DOLAN_ai 20.0.1.37.0`: "¿Qué clientes me deben?" (también "quién me debe", "deudores") responde con el saldo a cobrar por cliente de todas las compañías seleccionadas, con lo vencido, sin pasar por el modelo; antes el modelo miraba una sola cuenta contable de una compañía y podía listar cuentas de banco como clientes. El modelo también tiene la herramienta `receivables_by_partner`. "Del año", "en el año" y "en lo que va del año" ya toman el año en curso en reportes y tableros (antes quedaba el mes actual). Se quitó un warning de traducción que se repetía en el log en cada resumen de facturación. Si la compañía actual no tiene conexión de IA propia, el chat usa la conexión activa de otra compañía en lugar de crear un proveedor ChatGPT vacío que dejaba el chat sin responder.
- `DOLAN_ai 20.0.1.35.0`: el chat ya no inventa consultas cuando ChatGPT falla (antes listaba contactos o ventas genéricos y devolvía JSON crudo); informa el motivo y, si se agotó el cupo del plan, cuándo se renueva, sin volver a llamar al proveedor hasta entonces. Los atajos de contactos y caja ya no capturan pedidos de facturación, cobranzas o saldos de un cliente. Solo un administrador puede cambiar el modelo de la compañía desde el chat. Cada respuesta tiene un presupuesto de tiempo (80 s por defecto, parámetro `dolan_ai.response_budget_seconds`) para no superar el corte de proxies y túneles; si la conexión se corta (502/520/524) el chat espera y recupera la respuesta guardada en lugar de pedir reintentar, y un reintento no duplica la conversación. Las herramientas se pueden encadenar hasta tres rondas, el catálogo de modelos se guarda una hora y la renovación del token no bloquea a otros usuarios durante la respuesta.
- `DOLAN_ai 20.0.1.33.0`: la sidebar del historial se cierra al elegir una conversación (incluida la que ya está abierta) o al tocar fuera; el historial identifica de forma visible el chat actual.

### Cambiado
- `DOLAN_ai 20.0.1.38.0`: el selector de modelos del chat es un buscador (por ejemplo "gpt-6 luna" o "claude") y lista primero los modelos más nuevos del proveedor; antes era una lista desplegable de cientos de modelos en orden alfabético. La cabecera del chat muestra el nombre del asistente y debajo el proveedor y el modelo en uso ("OpenRouter · OpenAI: GPT-6 Luna", "OpenAI · …"). Los avisos del chat ya no dicen "ChatGPT": nombran al proveedor (OpenAI, OpenRouter u Ollama).
- `DOLAN_theme 20.0.2.71.0`: el escritorio de usuarios nuevos arranca en orden «Personalizado» con Facturación, Ventas, Contabilidad, Compras, Inventario y POS primero; luego carpetas y el resto. En instalaciones con perfil Comercio, POS queda como favorito. No modifica escritorios ya personalizados.
- `DOLAN_l10n_ar_afip 20.0.1.35.0`: el listado sustituye **Impuestos no incluidos** por **IVA** (solo muestra IVA ARCA para compañías Responsable Inscripto), y elimina **Cantidad por pagar**.
- `DOLAN_l10n_ar_afip 20.0.1.34.0`: listado de facturas más compacto: oculta **Estado ARCA**, conserva **CAE**, muestra fecha y vencimiento en formato `dd/MM/yyyy` y ordena por fecha y número descendentes.
- `DOLAN_l10n_ar_afip 20.0.1.33.0`: el listado de facturas agrega la columna **CAE** con un tilde verde cuando el comprobante tiene código de autorización.

### Cambiado
- `DOLAN_l10n_ar_afip 20.0.1.31.0`: las facturas y notas argentinas muestran **Borrador (sin CAE)** cuando están publicadas contablemente pero aún no cuentan con autorización ARCA; al recibir CAE muestran el estado fiscal. El estado contable real de Odoo permanece intacto.

### Corregido
- `DOLAN_l10n_ar_afip 20.0.1.30.0`: La consulta de condiciones de IVA usa el nodo SOAP esperado por WSFE producción; el envío CAE ahora aplica TLS 1.2 y el mismo ajuste de DH que las consultas de solo lectura, sin desactivar validación de certificados. Se muestran códigos y mensajes de rechazos de ARCA sin exponer credenciales.

### Cambiado
- `DOLAN_l10n_ar_afip 20.0.1.26.0`: Encabezados del PDF para comprobantes distintos de letra A en español: **Precio Unitario** y **Total** en lugar de *Unit Price* y *Amount*.

### Cambiado
- `DOLAN_l10n_ar_afip 20.0.1.25.0`: Factura B mantiene el total con IVA incluido, oculta el renglón separado del IVA, elimina el bloque duplicado de transparencia y deja una única leyenda `Régimen de Transparencia Fiscal al Consumidor (Ley 27.743) — IVA Contenido` al pie. La URL predeterminada de términos no se imprime como nota.

### Corregido
- `DOLAN_accounting 20.0.1.8.0`: **Análisis de facturas** agrupa por mes y comprobante para evitar mostrar varias filas de análisis de líneas como si fueran documentos duplicados.

### Corregido
- `DOLAN_l10n_ar_afip 20.0.1.24.0`: Padrón asigna explícitamente **IVA Exento** (impuesto ARCA 32) e **IVA No Alcanzado** (34) cuando la respuesta no presenta otro régimen de IVA en conflicto. Las combinaciones ambiguas y CUIT sin impuestos activos siguen sin inferencia.
- El mapeo de provincia normaliza acentos y reconoce las etiquetas ARCA **CIUDAD AUTONOMA BUENOS AIRES**, **CABA** y **CAPITAL FEDERAL** como Ciudad Autónoma de Buenos Aires.

### Agregado
- `DOLAN_l10n_ar_afip 20.0.1.22.0`: nueva columna **Monto IVA** por línea en el PDF de comprobantes letra **A** (FA/NC/ND), calculada como `price_total - price_subtotal` de cada línea; las filas de sección ajustan su colspan para mantener la alineación.
- `LICENSE` con el texto oficial LGPL-3.0 y este `CHANGELOG.md`.
- Workflow de CI (GitHub Actions): validación estática de addons, vistas XML/RNG y suite de tests en Docker.
- `.env.example` documentado; los secretos de `docker-compose.yml` pasan a variables de entorno.

### Cambiado
- `DOLAN_l10n_ar_afip 20.0.1.23.0`: en comprobantes letra **A**, la tabla de líneas muestra **Precio s/IVA** y su última columna pasa a ser **Total** (`price_total` = neto + IVA), en lugar del importe neto. La herencia se aplica sobre la plantilla primaria de `l10n_ar` para evitar que su encabezado pise el personalizado.
- `README.md`: la tabla de módulos refleja los 13 módulos actuales e incorpora `DOLAN_whatsapp`.

### Corregido
- Impresión de facturas: se instala **wkhtmltopdf 0.12.6.1 (Qt parcheado)** en la imagen Docker; Odoo dejaba de generar PDF y caía a una vista previa HTML ("You need Wkhtmltopdf to print a pdf version of the reports"). La impresión vuelve a producir el PDF fiscal independientemente del modo claro/oscuro del backend.
- `DOLAN_l10n_ar_afip 20.0.1.17.0`: el reporte impreso ahora embebe la **imagen del QR oficial RG 4892** (antes solo mostraba la URL en texto), generada en servidor como data URI compatible con wkhtmltopdf.
- `DOLAN_theme 20.0.2.3.0` — contraste del modo oscuro en 4 frentes:
  - Menú **Acciones** (cog `.o_btn_circle`): el fondo se pinta en un `::before` con variables `--btn-*`; se redefinen para que el glifo ⋮ blanco sea visible.
  - **Compras**: Odoo compila Bootstrap con `$prefix` vacío, así que las utilidades `.bg-dark-subtle`/`text-dark-emphasis` consumen `--dark-bg-subtle` (sin `bs-`); se define la escala subtle/emphasis/border completa en ambas grafías, más `.bg-100..400` y empty states (`.o_view_nocontent`).
  - **Taller**: placeholders kanban `.bg-300` y textos de empty state legibles.
  - **Tableros**: el toggle de modo oscuro ahora sincroniza la cookie nativa `color_scheme=dark` (en ambos toggles: drawer y command palette), así o-spreadsheet activa su clase `.dark` y su filtro `--os-dark-mode-filter`. Se eliminan los overrides propios sobre elementos `.os-theme-dependant` (doble inversión que dejaba franjas blancas) y se invierten las figuras-imagen (charts embebidos como `<img>`, las únicas sin `os-theme-dependant`) con el mismo filtro nativo.
- `DOLAN_theme 20.0.2.4.0`: tarjetas del dashboard de Ventas (`.o_dashboard_card_*`) con fondos pastel ilegibles en oscuro. Odoo trae variante oscura (`dashboard.dark.scss`) pero solo se sirve con `web.assets_web_dark`, que la CE nunca carga (`ir_http.color_scheme()` está fijo en `"light"`); se tematiza la paleta de las 4 tarjetas (purple/cyan/orange/red) en el CSS propio.
- `DOLAN_theme 20.0.2.5.0`: notificaciones toast (`.o_notification`) blancas con texto claro en oscuro; pasan a la superficie oscura estándar. Verificación visual de formularios (factura, producto, contacto) en modo oscuro sin problemas de contraste.
- `DOLAN_l10n_ar_afip 20.0.1.18.0`: rediseño del bloque ARCA del PDF de factura/NC. El grid flex de Bootstrap se superponía en wkhtmltopdf (texto legal pisando el QR); se reemplaza por layout de tabla, el QR crece de 96px a 30mm (generado con `box_size=8` para impresión nítida) y es clicable (abre la verificación en ARCA), se elimina la URL textual redundante y el CAE/vencimiento queda alineado a la derecha.
- `DOLAN_l10n_ar_afip 20.0.1.21.0`: el cuadro NOTA pasa a flotar a la **izquierda del cuadro de totales** (56% del ancho), aprovechando el espacio vacío del pie y compactando su altura.
- `DOLAN_l10n_ar_afip 20.0.1.20.0` — totales y bloque ARCA/CAE fijados al fondo de la hoja:
  - `.page` pasa a `display: table` con altura calibrada (240mm) y la fila de líneas absorbe el espacio sobrante, dejando NOTA + totales + Ley 27.743 + ARCA/CAE pegados al margen inferior. Se descartó `position: absolute` (wkhtmltopdf no estira `.page` con `min-height` menor a una hoja) y la medición por JS (`window.innerHeight` llega en 0 por el `html{height:0}` del minimal_layout). Solo aplica a los reportes de factura (`data-report-id` de `account.account_invoices` / `account.account_invoices_without_payment`); si el contenido supera una hoja el pie queda al final sin páginas en blanco extra.
  - Fuente del cuadro NOTA reducida a 12px.
- `DOLAN_l10n_ar_afip 20.0.1.19.0` — pie del PDF de factura/NC reordenado y corrección del "tachado" en pagos:
  - Nuevo **cuadro NOTA** a ancho completo para la narración del comprobante (antes texto suelto en gris amontonado junto al QR), ubicado inmediatamente después de las líneas.
  - El **cuadro de totales** (con pagos y "Cantidad por pagar") queda debajo de la NOTA, y el **bloque ARCA/CAE + Ley 27.743** pasa a ser lo último del comprobante (`clear: both` para bajarlo del float de totales en wkhtmltopdf).
  - **Fix "Pagado el ..." tachado**: wkhtmltopdf pinta los bordes definidos a nivel `<tr>` desplazados ~media fila hacia abajo (la regla `border-top` de `tr.o_total` de `web/report_tables.scss` caía sobre la fila de pago). Se anula el borde a nivel fila y se repone a nivel celda vía `web.report_assets_common` (`static/src/css/report_dolan_ar.css`).

## [2026-11-01]

### Agregado
- `DOLAN_whatsapp 20.0.1.0.0`: integración WhatsApp vía WAHA (webhook, cuentas y mensajes), instalado con icono SVG de app.
- `DOLAN_theme`: PWA, barra inferior móvil, buscador global y controladores web nuevos.
- `DOLAN_l10n_ar_afip`: autocompletado de borrador de formulario Padrón vía JS.
- Evidencia QA de instaladores Bash/PowerShell verificados end-to-end en Docker limpio (perfil full, 187 módulos, 13/13 DOLAN, HTTP 200).

### Cambiado
- Consolidación de la auditoría `recovery/rea-audit`: 140+ evidencias QA de etapas E1–E3 (2026-10-28 a 2026-10-31).
- `.gitignore`: se ignoran `/tmp/`, `/TEST/`, `/certs/`, `/BACKs/` y `.env`.

## [2026-10-30]

### Agregado
- `DOLAN_ai 20.0.1.22.0`: selector de modelos OpenAI obtenidos dinámicamente, acciones contextuales protegidas, fallback legible de `search_read`/`read_group` (37 post-tests).
- `DOLAN_ocr 20.0.1.7.0`: decodificación local de QR AFIP desde URL, PNG/JPEG y PDF rasterizado; advertencias de diferencia QR/total en UI (15 post-tests).
- Restauración del backup real multi-empresa (`dolan_real_copy_20261029`) con certificados ARCA/AFIP de 3 razones sociales y migración de 189 comprobantes con CAE.

### Cambiado
- `DOLAN_ai`: UX Copilot con dock lateral de 440px, píldora flotante de minimización e icono vectorial Odoo 20.
- `DOLAN_theme 20.0.2.0.0`: toggle OWL 3 robusto en navbar y systray.

## [2026-10-29]

### Agregado
- `DOLAN_accounting 20.0.1.7.0`: cierre de ejercicio con asiento de refundición/apertura, reclasificación de deuda corriente/no corriente y desembolso de préstamos idempotente.
- `DOLAN_l10n_ar_afip 20.0.1.16.0`: Padrón ARCA (`getPersona_v2`) con ticket WSAA por compañía, MercadoPago y banca argentina.

## [2026-10-28]

### Agregado
- WSFE: facturas y notas A/B/C en ARS con IVA, no gravado/exento y tributos porcentuales mapeados al catálogo ARCA; recuperación segura de CAE (63 post-tests).
- `DOLAN_subscription 20.0.1.1.0` y `DOLAN_renting 20.0.1.1.0`: integración con `sale.order`, MRR/ARR/Churn y ciclo retiro-devolución-mora.
- `DOLAN_stock_mrp 20.0.1.1.0`: barcode, Shop Floor y Calidad; `DOLAN_pos 20.0.1.2.0`: KDS multi-estación y cobro de cuenta corriente.
- `DOLAN_knowledge_bi 20.0.1.1.0` y `DOLAN_views 20.0.1.2.0`: wiki RAG, tableros BI y vistas OWL 3 Gantt/Cohort/Grid/Map.
- Semilla demo integral idempotente (`dolan_demo_integral`); regresión global de 158–173 post-tests sin fallos.

---

> Estado de aceptación detallado por etapa: ver `docs/implementation/MASTER_STATUS.md`, `docs/implementation/KNOWN_GAPS.md` y `docs/implementation/PENDING_ACCEPTANCE.md`.
