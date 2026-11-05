# PRD (Product Requirements Document): Suite `DOLAN_*` para Odoo CE 20

**Proyecto:** `Odoo20-REA` — Distribución ERP Self-Hosted para Argentina  
**Versión Objetivo:** Odoo Community Edition `20.0` (OWL 3 / Python 3.12+ / PostgreSQL 17)  
**Referencia Funcional:** Odoo Community Edition 20.0  
**Base de Despliegue:** [`docs/crear_odoo20.sh`](./docs/crear_odoo20.sh)  
**Licencia de todo el código propio:** `LGPL-3` (100% Clean-Room, sin código propietario `OEEL-1` ni dependencias IAP pagas)

---

## 1. Resumen Ejecutivo y Objetivos del Producto

El objetivo de este proyecto es construir una distribución modular, multiempresa y autodesplegable de **Odoo CE 20** para organizaciones en Argentina, con funcionalidades fiscales y operativas propias, evitando dependencias de licencias privativas o créditos IAP cuando sea posible.

### Principios de Diseño Legal y Técnico
1. **Clean-Room & Cumplimiento de Licencias (`LGPL-3`)**:
   - Ningún archivo de código propietario de Odoo Enterprise es copiado.
   - Se relevaron contratos de datos de Odoo Community (modelos, campos, menús e interfaces) para diseñar extensiones compatibles con la versión objetivo.
   - Toda la lógica backend (Python) y frontend (OWL 3) de los módulos `DOLAN_*` se desarrolla desde cero bajo licencia `LGPL-3`, apoyándose en Odoo CE 20 y en los repositorios abiertos de **IngAdhoc** (`branch 20.0`).
2. **Nomenclatura Modular `DOLAN_*`**:
   - Todos los módulos propios llevan el prefijo `DOLAN_` para que desde el menú **Aplicaciones** (o desde el autoinstalador por línea de comandos) se pueda filtrar por `DOLAN_` y activar únicamente los módulos requeridos por cada cliente.
3. **Compatibilidad Nativa con OWL 3 (Odoo 20)**:
   - Los componentes JS/XML de `DOLAN_*` deben usar las APIs compatibles con Odoo 20 y su registro de servicios web.
4. **Configuración por Defecto Argentina (`es_AR` / `es_419`) y Multi-Empresa**:
   - El despliegue inicializa automáticamente idioma español argentino/latinoamericano, moneda `ARS`, país `Argentina`, huso horario `America/Buenos_Aires`, plan de cuentas argentino, tipos de comprobantes LATAM y soporte multi-CUIT (Multi-Empresa).

---

## 2. Inventario de Módulos a Reutilizar (Sin Desarrollo Propio)

### 2.1 Módulos Core de Odoo CE 20 (`LGPL-3` — 169 módulos instalados en la demo)
Odoo CE 20 ya incluye de forma nativa los siguientes módulos clave:

| Área Funcional | Módulos Core Odoo CE 20 (`LGPL-3`) que se reutilizan directamente |
| :--- | :--- |
| **Localización Argentina Base (co-desarrollada por ADHOC SA en CE)** | `l10n_ar` (v20.0.3.7 — Plan de cuentas, responsabilidades ARCA, actividades ARCA, impuestos IVA/IIBB/Internos), `l10n_latam_invoice_document` (Letras A, B, C, E, M, MiPyME FCE, NDC/NDD), `l10n_latam_check` (Cheques propios, de terceros y Echeq), `l10n_ar_withholding` (Retenciones de Ganancias e IIBB en pagos, escalas `l10n_ar.earnings.scale`), `l10n_account_withholding_tax`, `l10n_account_withholding_tax_pos`, `l10n_ar_pos`, `l10n_ar_stock`, `certificate` (Certificados X.509 `certificate.certificate` y claves privadas `certificate.key`). |
| **Comercial, CRM y Ventas** | `crm`, `crm_iap_mine`, `sale_management`, `sale`, `sale_crm`, `sale_margin`, `sale_pdf_quote_builder`, `sale_project`, `sale_purchase`, `sale_service`, `sale_stock`, `contacts`, `utm`. |
| **Punto de Venta y Gastronomía** | `point_of_sale`, `pos_restaurant`, `pos_hr`, `pos_sale`, `pos_self_order`, `pos_online_payment`, `pos_discount`, `pos_loyalty`. |
| **Facturación y Finanzas Base** | `account`, `account_debit_note`, `account_edi_ubl_cii`, `account_payment`, `account_peppol`, `account_qr_code_emv`, `analytic`. |
| **Compras, Stock y Logística** | `purchase`, `purchase_stock`, ` purchase_mrp`, `stock`, `stock_account`, `stock_delivery`, `stock_landed_costs`, `stock_picking_batch`, `barcodes`, `barcodes_gs1_nomenclature`, `delivery`. |
| **Manufactura y Mantenimiento** | `mrp`, `mrp_account`, `mrp_subcontracting`, `maintenance`, `hr_maintenance`. |
| **Proyectos, RRHH y Flota** | `project`, `project_todo`, `project_hr_expense`, `project_hr_skills`, `hr`, `hr_expense`, `hr_skills`, `hr_attendance`, `hr_holidays`, `hr_hourly_cost`, `fleet`, `calendar`. |
| **Comunicación y Base Técnica** | `mail`, `mail_bot`, `mail_group`, `discuss`, `base`, `web`, `web_tour`, `web_hierarchy`, `base_automation`, `base_import`, `portal`, `auth_signup`, `auth_passkey`, `auth_totp`, `google_gmail`. |

### 2.2 Módulos Comunitarios de IngAdhoc (`branch 20.0` en `crear_odoo20.sh`)
Se descargan automáticamente desde los 6 repositorios oficiales de **IngAdhoc** en su rama `20.0`:

| Repositorio GitHub (`branch 20.0`) | Módulos Reutilizados y Estado en 20.0 |
| :--- | :--- |
| `ingadhoc/odoo-argentina-ce` | **`l10n_ar_fiscal_ws`**: Webservices AFIP/ARCA (WSAA y WSFEv1 con `pyafipws`). Habilitado automáticamente en `crear_odoo20.sh` (`installable: True`, suite de 38 tests en verde). |
| `ingadhoc/odoo-argentina` | `l10n_ar_ux`, `l10n_ar_tax`, `l10n_ar_bank`, `l10n_ar_purchase` (se complementan y estabilizan desde `DOLAN_l10n_ar_afip` mientras ADHOC finaliza su migración 20.0). |
| `ingadhoc/argentina-sale` | `l10n_ar_sale`, `l10n_ar_stock`, talonarios preimpresos y remitos argentinos. |
| `ingadhoc/account-financial-tools` | `account_internal_transfer` y utilidades financieras contables. |
| `ingadhoc/account-payment` | `account_payment_pro` / mejoras de recibos y órdenes de pago agrupadas. |
| `ingadhoc/sale` | `sale_barcode`, `sale_price_checker` (instalables en 20.0), `sale_ux`. |

---

## 3. Especificación de los 12 Módulos Propios a Desarrollar (`DOLAN_*`)

El catálogo de extensiones propias se desarrolla en módulos separados bajo `./addons/`:

### Módulo 1: `DOLAN_base` (`DOLAN - Core, Multi-Empresa & Inicialización Argentina`)
- **Reemplaza**: `saas_trial`, `saas_dashboard_activities`, configuración inicial manual.
- **Requerimientos funcionales**:
  1. Hook `post_init_hook` que oculta automáticamente todas las tarjetas promocionales `OEEL-1` del menú Aplicaciones (`application = False` cuando `license = 'OEEL-1'`) y desactiva alertas de vencimiento de suscripción (`database.expiration_date`).
  2. Configura por defecto idioma `es_419`/`es_AR`, país `Argentina` (`base.ar`), moneda `ARS` activa, huso horario `America/Buenos_Aires` y parámetro `l10n_ar_fiscal_ws.env_type = 'homologation'`.
  3. **Asistente Multi-Empresa (`dolan.company.onboarding.wizard`)**: Permite dar de alta una nueva empresa del grupo con su CUIT, Condición frente a ARCA (`IVA Responsable Inscripto`, `Monotributo`, `Exento`), Punto de Venta AFIP, plan de cuentas argentino (`l10n_ar`) y diarios de cheques/retenciones en un solo paso.
  4. **Gestor de Perfiles de Cliente (`dolan.client.profile`)**: Permite activar/desactivar paquetes de módulos `DOLAN_*` según el rubro del cliente (Comercio, Industria, Gastronomía, Servicios, Full).

### Módulo 2: `DOLAN_theme` (`DOLAN - Estética Web & Mobile Enterprise OWL 3`)
- **Reemplaza**: `web_enterprise`, `web_mobile`, `mail_enterprise`, `mail_mobile`, `hr_mobile`, `contacts_enterprise`, `crm_enterprise`, `sale_enterprise`, `stock_enterprise`, `project_enterprise`, `maintenance_enterprise` (y los antiguos `dolan_ui`).
- **Requerimientos funcionales**:
  1. **App Drawer / Home Menu (OWL 3)**: Pantalla de inicio a pantalla completa con grilla de íconos de aplicaciones, fondo personalizable por empresa, buscador instantáneo de aplicaciones y menús al empezar a tipear, y navegación con flechas de teclado + `Enter` + tecla `Escape`.
  2. **Paleta y Tipografía**: Variables CSS/SCSS alineadas con Odoo 20 Web (`#714B67` primario, degradado de fondo, bordes redondeados modernos, soporte de **Modo Claro / Modo Oscuro** persistente por usuario).
  3. **Diseño Responsive Mobile**: Barra superior adaptativa, formularios con hoja (`o_form_sheet`) a ancho completo opcional, chatter lateral en pantallas anchas e inferior en móviles, y encabezados fijos en listas.
  4. **Ordenamiento Inteligente de Menús Raíz**: Organiza las aplicaciones disponibles por flujos de trabajo y preferencias del usuario.

### Módulo 3: `DOLAN_l10n_ar_afip` (`DOLAN - Facturación Electrónica ARCA/AFIP, Padrón, QR y Libro IVA`)
- **Reemplaza**: `l10n_ar_edi`, `l10n_ar_reports` (integrándose con `l10n_ar`, `certificate` y `l10n_ar_fiscal_ws` de ADHOC).
- **Requerimientos funcionales**:
  1. **Modelos de Conexión ARCA/AFIP compatibles con el esquema Odoo 20**:
     - `l10n_ar.afipws.connection`: Almacena y renueva Tickets de Acceso (`token`, `sign`, `uniqueid`, `generation_time`, `expiration_time`) contra WSAA (Homologación `wsaahomo.afip.gov.ar` y Producción `wsaa.afip.gov.ar`) usando `certificate.certificate` y `certificate.key` por compañía (`company_id`).
     - `l10n_ar_afip.ws.consult`: Asistente para consultar el último comprobante autorizado (`FECompUltimoAutorizado`) y recuperar datos de un comprobante emitido en ARCA (`FECompConsultar`).
  2. **Emisión de CAE y CAEA (WSFEv1, WSFEXv1, WSMTXCA)**:
     - Obtención de CAE y fecha de vencimiento de CAE al validar facturas de cliente (Facturas A, B, C, E, Factura de Crédito Electrónica MiPyME FCE con CBU y opción de transmisión SCA/ADC, Notas de Crédito y Débito con comprobantes asociados).
  3. **Consulta de Padrón ARCA por CUIT**:
     - Botón *"Actualizar desde Padrón ARCA"* en `res.partner` que consulta razón social, dirección, provincia, código postal, condición frente al IVA y actividad principal (`l10n_ar.arca.activity`).
  4. **Impresión PDF Reglamentaria y Reportes Fiscales (`l10n_ar_reports`)**:
     - Generación automática del **Código QR Oficial de ARCA/AFIP** (`https://www.afip.gob.ar/fe/qr/?p=...` con payload JSON en Base64) en el PDF de la factura.
     - Leyenda de **Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)** mostrando el IVA contenido en comprobantes B/C.
     - **Exportador de Libro IVA Digital (Compras y Ventas)**: Generación de los 4 archivos TXT posicionales reglamentarios de AFIP/ARCA (`LIBRO_IVA_DIGITAL_VENTAS_CBTE`, `VENTAS_ALICUOTAS`, `COMPRAS_CBTE`, `COMPRAS_ALICUOTAS`) y archivo TXT de **SICORE** (retenciones y percepciones).

### Módulo 4: `DOLAN_accounting` (`DOLAN - Contabilidad Pro, Conciliación, Activos, Follow-up y Reportes`)
- **Reemplaza**: `accountant`, `account_accountant`, `account_reports`, `account_asset`, `account_followup`, `account_loans`, `account_fiscal_categories`, `account_bank_statement_import*` (CSV/OFX/CAMT), `account_online_synchronization`, `analytic_enterprise`, `*_accountant` bridges.
- **Requerimientos funcionales**:
  1. **Aplicación `Contabilidad` (`accountant`)**: Habilita el menú raíz **Contabilidad** (secuencia 60) con acceso completo a Asientos Contables, Apuntes Contables, Plan de Cuentas, Conciliación, Activos, Préstamos y Reportes Financieros.
  2. **Conciliación Bancaria Interactiva y Extractos**:
     - Importador universal de extractos bancarios en formatos **CSV, Excel (XLSX), OFX y CAMT.053**.
     - Asistente/vista de conciliación bancaria rápida para emparejar líneas de extracto con facturas, pagos y cheques (`l10n_latam_check`), con modelos de conciliación (gastos bancarios, impuesto al cheque Ley 25.413).
  3. **Gestión de Activos Fijos (`dolan.account.asset`) y Préstamos (`dolan.account.loan`)**:
     - Cálculo automático de cuadros de amortización (lineal/depreciación mensual o anual) y contabilización por cron.
     - Gestión de préstamos financieros con tabla de amortización (sistema francés/alemán), separación de capital e intereses.
  4. **Seguimiento de Deudores (`dolan.account.followup`)**:
     - Niveles de reclamo configurables por días de mora, envío automático de estado de cuenta por correo/WhatsApp y bloqueo comercial opcional.
  5. **Motor de Reportes Contables Dinámicos**:
     - Balance General, Estado de Resultados (P&L), Libro Mayor, Balance de Sumas y Saldos, Antigüedad de Saldos (Deudores/Acreedores) y Flujo de Caja, con filtros por fecha, compañía, cuentas analíticas y exportación a XLSX y PDF.

### Módulo 5: `DOLAN_ai` (`DOLAN - IA Agéntica Odoo 20 + OAuth 2.0 PKCE de ChatGPT estilo OpenCode/Pi`)
- **Reemplaza**: Los 20 módulos `ai*` de Odoo 20 (`ai`, `ai_agentic`, `ai_agentic_knowledge`, `ai_fields`, `ai_server_actions`, `ai_mcp`, `ai_portal`, `ai_auto_install`, `ai_account`, `ai_account_reports`, `ai_crm`, `ai_sale`, `ai_sale_margin`, `ai_sale_stock`, `ai_purchase`, `ai_stock`, `ai_project`, `ai_calendar`, `ai_product`, `ai_knowledge`).
- **Requerimientos funcionales**:
  1. **Conector OAuth 2.0 PKCE con ChatGPT (`auth.openai.com` — Estilo OpenCode / Pi)**:
     - Modelo `dolan.ai.provider` (multi-empresa) con soporte para:
       - **Modo `chatgpt_oauth` (Por defecto)**: Flujo OAuth 2.0 + PKCE (`S256`) contra `https://auth.openai.com/oauth/authorize` y `https://auth.openai.com/oauth/token` (usando el `client_id` público de clientes CLI como OpenCode/Pi `app_EMoamEEZ73f0CkXaXp7hrann` o personalizado).
       - Incluye botón en Ajustes *"Vincular cuenta de ChatGPT (OAuth)"* que genera el par `code_verifier`/`code_challenge`, abre la autorización y captura el callback (directamente en despliegues locales o pegando la URL/código de callback en despliegues VPS remotos), almacenando `access_token`, `refresh_token`, `id_token`, `account_id` y renovando el token automáticamente antes de su expiración.
       - **Modos alternativos**: API Key compatible con OpenAI (`/v1/chat/completions`), Google Gemini, Anthropic Claude o modelos locales vía **Ollama / vLLM**.
  2. **Modelos de Datos 100% Compatibles con Odoo 20 (según evidencia REA `ev_e1d7400d...`)**:
     - `ai.agent`: Agentes preconfigurados con instrucciones seguras y adaptables a cada instalación.
     - `ai.agent.source`: Fuentes de conocimiento adjuntas al agente (archivos PDF/TXT, páginas web, artículos de `DOLAN_knowledge_bi`).
     - `ai.skill`: Las 12 habilidades nativas relevadas en la demo (*Shape View*, *Search Database*, *Update Records*, *Create Records*, *Generate Image*, *Web Search*, *Accounting Report Analysis*, *Accounting*, *Accounting Audit Evidence*, *Self Update*, *Build Automation*, *Create Lead (Livechat)*) implementadas como herramientas (`tools` / Function Calling) que consultan y operan sobre el ORM de Odoo respetando los permisos del usuario activo.
     - `ai.composer` y `ai.prompt.button`: Las 14 reglas de interfaz y los 35 botones de prompts rápidos traducidos al español argentino.
     - `ai.session` y `ai.session.event`: Sesiones de chat persistentes con ejecución multi-turno de herramientas.
  3. **Integración UI en OWL 3**:
     - Aplicación **IA** en el menú principal (secuencia 50) para gestionar Agentes, Skills, Prompts y Sesiones.
     - Botón **Ask AI** en el Systray (barra superior) que abre el panel lateral/modal de conversación con *Odoo AI* desde cualquier pantalla, pasando el modelo y registro activo (`res_model`, `res_id`) como contexto.
     - Asistente de redacción y resumen en el **Chatter** de cualquier documento (Presupuestos, Facturas, Tareas, Oportunidades CRM).
     - Acciones de servidor con IA (`ai_server_actions`) y campos autocompletados por IA (`ai_fields`).

### Módulo 6: `DOLAN_ocr` (`DOLAN - Extracción OCR de Facturas, Gastos y Extractos con IA`)
- **Reemplaza**: `iap_extract`, `account_extract`, `account_invoice_extract`, `account_invoice_extract_purchase`, `account_bank_statement_extract`, `account_loans_extract`, `hr_expense_extract`, `hr_expense_predict_product`.
- **Requerimientos funcionales**:
  1. Botón **"Digitalizar con DOLAN IA"** en Facturas de Proveedor (`account.move`), Gastos (`hr.expense`) y Extractos Bancarios.
  2. **Doble motor sin costo IAP**:
     - Primero intenta decodificar el **Código QR de AFIP/ARCA** presente en las facturas electrónicas argentinas (extrayendo con 100% de exactitud CUIT emisor, Punto de Venta, Tipo y Número de Comprobante, Fecha, Importe Total, Moneda, CAE).
     - Luego utiliza el conector multimodal de `DOLAN_ai` (visión de ChatGPT OAuth / modelo configurado) + extracción de texto PDF para completar las líneas de producto, alícuotas de IVA (21%, 10.5%, 27%), percepciones de IIBB/IVA y emparejar con la Orden de Compra.

### Módulo 7: `DOLAN_views` (`DOLAN - Vistas Avanzadas OWL 3: Gantt, Cohort, Grid y Map`)
- **Reemplaza**: `web_gantt`, `web_cohort`, `web_grid`, `web_map`, `hr_gantt`.
- **Requerimientos funcionales**:
  1. Registro en Odoo 20 (`registry.category("views")`) de los 4 tipos de vista adicionales en OWL 3:
     - **`gantt`**: Línea de tiempo interactiva con barras arrastrables (drag & drop de fechas), agrupación por responsable/proyecto/centro de producción y escala Día/Semana/Mes/Año.
     - **`cohort`**: Tabla de retención porcentual por períodos de tiempo (para suscripciones, oportunidades CRM y pedidos).
     - **`grid`**: Matriz editable por semana/mes (ideal para carga rápida de horas o disponibilidad).
     - **`map`**: Vista de mapa interactivo utilizando **Leaflet + OpenStreetMap + Nominatim** (100% gratuito y sin necesidad de token SaaS de Mapbox).

### Módulo 8: `DOLAN_pos` (`DOLAN - PoS Kitchen Display, Customer Tracking y Cuenta Corriente`)
- **Reemplaza**: `pos_enterprise`, `pos_restaurant_preparation_display`, `pos_self_order_preparation_display`, `pos_order_tracking_display`, `pos_settle_due`, `pos_stock_enterprise`.
- **Requerimientos funcionales**:
  1. **Kitchen Display (Pantalla de Cocina)**: Menú raíz `Kitchen Display` (secuencia 51) y controlador/vista OWL 3 en tiempo real (vía `bus.bus`) que muestra comandas pendientes, en preparación y listas por categoría (Cocina, Barra, Postres), con cronómetro de demora y cambio de estado táctil.
  2. **Order Tracking Display**: Pantalla pública para clientes con dos columnas (*En Preparación* vs *Listo para Retirar*).
  3. **Liquidación de Cuenta Corriente en PoS (`pos_settle_due`)**: Permite cobrar facturas pendientes o saldos de cuenta corriente de un cliente directamente desde la caja del Punto de Venta.
  4. **Consulta de Stock por Almacén en PoS**: Muestra en la ficha del producto del PoS el stock disponible en tiempo real en cada depósito.

### Módulo 9: `DOLAN_stock_mrp` (`DOLAN - Código de Barras, Taller Shop Floor MRP II y Calidad`)
- **Reemplaza**: `stock_barcode`, `stock_barcode_mrp`, `mrp_workorder`, `mrp_workorder_hr_account`, `mrp_maintenance`, `quality`, `product_barcodelookup`.
- **Requerimientos funcionales**:
  1. **Aplicación `Código de Barras` (`stock_barcode`)**: Menú raíz (secuencia 155) con interfaz táctil adaptada a lectores láser USB/Bluetooth y cámara móvil para procesar Recepciones, Entregas, Transferencias Internas y Ajustes de Inventario escaneando EAN13/GS1/Ubicaciones.
  2. **Aplicación `Taller / Shop Floor` (`mrp_workorder`)**: Menú raíz (secuencia 146) con tarjetas por Centro de Producción y Orden de Trabajo, botones Iniciar / Pausar / Terminar, registro de operario (`hr.employee`), costeo horario de mano de obra, consumo de componentes y solicitud de mantenimiento desde planta.
  3. **Gestión de Calidad (`quality`)**: Puntos de control de calidad (`dolan.quality.point`), chequeos (`dolan.quality.check` tipo Aprobado/Fallido, Medición numérica o Foto) en recepciones/producción y Alertas de Calidad (`dolan.quality.alert`).

### Módulo 10: `DOLAN_subscription` (`DOLAN - Suscripciones y Facturación Recurrente`)
- **Reemplaza**: `sale_subscription`, `sale_subscription_stock`, `crm_sale_subscription`, `project_sale_subscription`, `pos_sale_subscription`.
- **Requerimientos funcionales**:
  1. Menú raíz `Suscripciones` (secuencia 40).
  2. Planes de recurrencia (Mensual, Bimestral, Trimestral, Semestral, Anual).
  3. Generación automática de facturas electrónicas (integradas con `DOLAN_l10n_ar_afip`) mediante tarea programada (`ir.cron`), envío por email, manejo de bajas/motivos de cancelación y tablero de métricas **MRR / ARR / Churn**.

### Módulo 11: `DOLAN_renting` (`DOLAN - Gestión de Alquileres / Rental`)
- **Reemplaza**: `sale_renting`, `sale_management_renting`, `sale_stock_renting`, `sale_mrp_renting`, `sale_renting_crm`, `sale_renting_project`, `sale_renting_pdf_quote_builder`, `pos_sale_stock_renting`.
- **Requerimientos funcionales**:
  1. Menú raíz `Alquiler` (secuencia 45).
  2. Marcado de productos como `Puede ser alquilado` (`is_rental = True`) con tarifas por Hora, Día, Semana o Mes.
  3. Calendario de disponibilidad y reservas de unidades/números de serie, asistentes de **Retiro (Pickup)** y **Devolución (Return)** con cálculo automático de recargo por devolución tardía.

### Módulo 12: `DOLAN_knowledge_bi` (`DOLAN - Base de Conocimiento Wiki & Tableros BI`)
- **Reemplaza**: `knowledge`, `accountant_knowledge`, `spreadsheet_edition`, `spreadsheet_dashboard_edition`, `spreadsheet_dashboard_*` (y el antiguo `dolan_dash`).
- **Requerimientos funcionales**:
  1. **Aplicación `Conocimiento` (`knowledge`)**: Menú raíz (secuencia 17) con árbol jerárquico de artículos colaborativos (`dolan.knowledge.article`), íconos, portadas, permisos por equipo/usuario, historial de versiones e integración automática como fuente de contexto RAG para `DOLAN_ai`.
  2. **Aplicación `Tableros` (`Dashboards`)**: Menú raíz (secuencia 37) con tableros ejecutivos preconfigurados en tiempo real para **Ventas, Facturación y Finanzas (ARS/USD), CRM, Punto de Venta, Inventario, Compras y Manufactura**, con tarjetas KPI, gráficos comparativos y exportación a planilla de cálculo.

---

## 4. Arquitectura del Autoinstalador (`crear_odoo20.sh` / `crear_odoo20.ps1`)

Tomando como base [`docs/crear_odoo20.sh`](./docs/crear_odoo20.sh), el instalador en la raíz del repositorio ofrecerá:
- **Soporte Multi-Plataforma**:
  - `crear_odoo20.sh` para servidores Linux (Ubuntu/Debian VPS) y WSL2.
  - `crear_odoo20.ps1` para entornos Windows con Docker Desktop.
- **Descarga Unificada**:
  1. Construye la imagen Docker basada en `odoo:20.0` con `pyafipws`, `m2crypto`, `qrcode`, `pdf417gen`, `python-barcode`, `openpyxl`, `ofxparse` y `httpx`.
  2. Descarga los 6 repositorios de **IngAdhoc** (`branch 20.0`) y habilita `l10n_ar_fiscal_ws`.
  3. Vincula todos los módulos propios `./addons/DOLAN_*`.
- **Selector de Perfiles de Instalación (`--profile`)**:
  - `--profile core`: `DOLAN_base,DOLAN_theme,DOLAN_l10n_ar_afip,DOLAN_accounting,DOLAN_ai,DOLAN_ocr`
  - `--profile comercio`: `core` + `DOLAN_pos,DOLAN_stock_mrp`
  - `--profile industria`: `core` + `DOLAN_stock_mrp,DOLAN_views`
  - `--profile servicios`: `core` + `DOLAN_subscription,DOLAN_renting,DOLAN_views,DOLAN_knowledge_bi`
  - `--profile full` (por defecto): Instala el catálogo DOLAN seleccionado y las aplicaciones Community compatibles.
