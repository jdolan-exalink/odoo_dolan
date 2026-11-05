# Arquitectura y plan maestro: Suite `DOLAN_*` sobre Odoo CE 20

## 1. Evidencia Obtenida con MCP REA

El análisis funcional tomó como referencia una instancia de Odoo 20 y sus flujos, modelos y menús observables.

- **Evidence IDs retenidos por REA**:
  - `ev_5bc0b24debfdbb59db75964bd6e29fafc25bd1cbe1d4cb39bc65ab64c75d97f1` (Sesión web, assets OWL, manifiesto PWA, `__session_info__`, `mail/store`).
  - `ev_9f983dc9d6b38ab73bf74df10cd6cf478c0927bc7b7c218d5082e434795c258e` (Inventario completo de 304 módulos instalados, menús raíz, modelos `ai.*` y `l10n_ar.*`, diarios contables y parámetros de sistema).
  - `ev_e1d7400d20e61630dd00df67be1bf73c3c946601e0cd2b7e605bc0dc1eb0215d` (Esquema detallado `ir.model.fields` de los modelos de IA y ARCA/AFIP, `ai.skill`, ajustes `res.config.settings`).
  - `ev_2a82e08dc25ce22cf96bd479893d6dfbc5fffa1d5bb17cc0e719c20f8431ef9b` (Prompts de sistema de `ai.agent`, reglas `ai.composer`, botones `ai.prompt.button` y datos fiscales de `res.company`).

### 1.1 Referencia funcional de Odoo 20
- **Versión del motor**: `20.0+e` (`server_version_info: [20, 0, 0, "final", 0, "e"]`, worker `saas-19.5-1`).
- **Configuración regional detectada**:
  - Idioma activo: `es_419` (Español América Latina / Argentina).
  - Zona horaria: `America/Argentina/Buenos_Aires`.
  - Moneda principal: `ARS` (`id: 19`, símbolo `\$`).
  - Condición frente a ARCA (ex-AFIP): `IVA Responsable Inscripto` (`l10n_ar.afip.responsibility.type` `id: 1`).
- **Distribución de los 304 módulos instalados**:
  - **169 módulos `LGPL-3` (Odoo Community Edition)**: ya vienen incluidos libremente en Odoo CE 20 (incluyendo `l10n_ar`, `l10n_latam_invoice_document`, `l10n_latam_check`, `l10n_ar_withholding`, `l10n_ar_pos`, `l10n_ar_stock`, `certificate`, `crm`, `sale_management`, `purchase`, `stock`, `mrp`, `point_of_sale`, `pos_restaurant`, `project`, `project_todo`, `hr`, `hr_expense`, `fleet`, `maintenance`).
  - **128 módulos `OEEL-1` (Enterprise)**: agrupados en 12 dominios funcionales que reemplazaremos mediante módulos limpios `DOLAN_*` (licencia `LGPL-3`) + base OCA/ADHOC.
  - **7 módulos `Other proprietary` (`saas_*`)**: exclusivos de la infraestructura cloud de Odoo.com (`saas_trial`, `saas_pos`, `saas_base_import`, etc.), innecesarios en despliegue self-hosted.

---

## 2. Mapa de Reemplazo: De 128 Módulos No-CE a la Suite `DOLAN_*`

En lugar de mantener 128 micro-módulos puente dispersos, consolidaremos toda la funcionalidad no-CE en **12 módulos modulares `DOLAN_*`** bajo licencia libre, permitiendo activar por cliente solo lo que necesite:

| Módulo `DOLAN_*` | Funcionalidades que amplía | Funcionalidades Clave y Base Open Source (CE + ADHOC/OCA) |
| :--- | :--- | :--- |
| **`DOLAN_theme_enterprise`** | `web_enterprise`, `web_mobile`, `mail_enterprise`, `mail_mobile`, `hr_mobile`, `contacts_enterprise`, `crm_enterprise`, `sale_enterprise`, `stock_enterprise`, `project_enterprise`, `maintenance_enterprise` | App Drawer (menú de inicio en grilla con íconos e imagen de fondo), paleta `#714B67` / modo oscuro, comando rápido (`Ctrl+K`), diseño responsive móvil, PWA manifest y vistas mejoradas. |
| **`DOLAN_views_pro`** | `web_gantt`, `web_cohort`, `web_grid`, `web_map`, `hr_gantt` | Vistas OWL nativas para **Gantt** (timeline interactivo), **Cohort** (retención), **Grid** (matriz temporal) y **Map** (OpenStreetMap/Leaflet sin depender de token SaaS). |
| **`DOLAN_ai_chatgpt`** | `ai`, `ai_agentic`, `ai_agentic_knowledge`, `ai_fields`, `ai_server_actions`, `ai_mcp`, `ai_portal`, `ai_auto_install`, `ai_account`, `ai_account_reports`, `ai_crm`, `ai_sale`, `ai_sale_margin`, `ai_sale_stock`, `ai_purchase`, `ai_stock`, `ai_project`, `ai_calendar`, `ai_product`, `ai_knowledge` | Clon funcional completo de la arquitectura de IA de Odoo 20 (`ai.agent`, `ai.session`, `ai.skill`, `ai.composer`, `ai.prompt.button`, `ai-chat` en Discuss, botón en systray y en chatter/HTML), conectado por **OAuth 2.0 PKCE de ChatGPT (estilo OpenCode / Pi)** y/o API compatible OpenAI. |
| **`DOLAN_l10n_ar_afip`** | `l10n_ar_edi`, `l10n_ar_reports` | Integración directa con **ARCA / AFIP** basada en la arquitectura de **IngAdhoc (`ingadhoc/odoo-argentina-ce` / `pyafipws`)** adaptada a Odoo 20: WSAA (Token/Sign con `certificate.certificate` y `certificate.key`), WSFEv1, WSFEXv1, WSMTXCA, consulta de padrón A5/A13, validación de comprobantes, QR reglamentario AFIP en PDF, Libro IVA Digital y subdiarios/SICORE. |
| **`DOLAN_accounting_pro`** | `accountant`, `account_accountant`, `account_reports`, `account_asset`, `account_followup`, `account_loans`, `account_fiscal_categories`, `account_bank_statement_import*` (CSV/OFX/CAMT), `account_online_synchronization`, `analytic_enterprise`, bridges `*_accountant` | Tablero contable completo, widget de conciliación bancaria interactivo, importador de extractos (CSV, OFX, CAMT, Excel), gestión de activos fijos y amortizaciones, seguimiento de deudores (`followup`), préstamos y reportes dinámicos (Balance General, Estado de Resultados, Mayor, Sumas y Saldos). |
| **`DOLAN_ocr_extract`** | `iap_extract`, `account_extract`, `account_invoice_extract`, `account_invoice_extract_purchase`, `account_bank_statement_extract`, `account_loans_extract`, `hr_expense_extract`, `hr_expense_predict_product` | Extracción inteligente de facturas de proveedor, tickets de gastos y extractos bancarios en PDF/imagen **sin créditos IAP de Odoo**, usando visión multimodal a través del mismo conector OAuth de `DOLAN_ai_chatgpt` + parser de QR/CUIT argentino. |
| **`DOLAN_knowledge`** | `knowledge`, `accountant_knowledge` | Base de conocimientos colaborativa tipo Notion: árbol jerárquico de artículos (`knowledge.article`), permisos por artículo/carpeta, plantillas, propiedades dinámicas e indexación RAG para los agentes de `DOLAN_ai_chatgpt`. |
| **`DOLAN_spreadsheet_bi`** | `spreadsheet_edition`, `spreadsheet_dashboard_edition`, `account_reports_spreadsheet`, `spreadsheet_sale_management`, `spreadsheet_dashboard_*` (8 módulos) | Edición de hojas de cálculo integradas sobre `@odoo/o-spreadsheet` (librería open-source de Odoo), inserción de pivotes/listas en vivo y constructor de tableros BI. |
| **`DOLAN_sale_subscription`** | `sale_subscription`, `sale_subscription_stock`, `crm_sale_subscription`, `project_sale_subscription`, `pos_sale_subscription` | Contratos de abono recurrente, facturación automática por cron, renovación, alertas de baja (churn/MRR) e integración con ventas, proyectos, stock y PoS. |
| **`DOLAN_sale_renting`** | `sale_renting`, `sale_management_renting`, `sale_stock_renting`, `sale_mrp_renting`, `sale_renting_crm`, `sale_renting_project`, `sale_renting_pdf_quote_builder`, `pos_sale_stock_renting` | Gestión de alquileres por período (horas/días/semanas), calendario Gantt de disponibilidad de stock en alquiler, retiro/devolución, recargos por demora y cotizador PDF. |
| **`DOLAN_stock_mrp_pro`** | `stock_barcode`, `stock_barcode_mrp`, `mrp_workorder`, `mrp_workorder_hr_account`, `mrp_maintenance`, `quality`, `product_barcodelookup` | Interfaz táctil de **Código de Barras** (recepciones, transferencias, inventario físico con lector láser o cámara), **Shop Floor (Taller MRP II)** con cronómetro por operario y controles de **Calidad**. |
| **`DOLAN_pos_pro`** | `pos_enterprise`, `pos_restaurant_preparation_display`, `pos_self_order_preparation_display`, `pos_order_tracking_display`, `pos_settle_due`, `pos_stock_enterprise` | **Kitchen Display (Pantalla de Cocina)** en tiempo real vía bus websocket, pantalla de seguimiento de pedidos para clientes, liquidación de cuentas corrientes de clientes en PoS y consulta de stock por sucursal. |

---

## 3. Especificación Técnica de los 3 Pilares Críticos

### 3.1 `DOLAN_ai`: Sign in with ChatGPT, Responses API y chat estilo ChatGPT

La conexión implementa el flujo **Sign in with ChatGPT para clientes open source**, documentado por OpenAI para herramientas abiertas y alojadas localmente. No reutiliza el client ID de OpenCode/Pi ni endpoints privados de `chatgpt.com`.

1. **Registro y PKCE**: En el primer enlace usa `client_id=dynamic_agent_client`, un `ext_agent_host_id` UUID persistente, `agent_name_hint=DOLAN AI`, `state`, `nonce` y PKCE S256.
2. **Permisos y callback**: Solicita identidad y uso del plan (`openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`) para el recurso `https://api.openai.com/v1`. El callback es `http://127.0.0.1:1455/auth/callback`; si el navegador no alcanza un listener local, se copia la URL completa y se pega en Odoo. El canje exige `state` coincidente y el `client_id` emitido por OpenAI.
3. **Validación y refresh**: El token se canjea en `https://auth.openai.com/api/accounts/oauth/token`. DOLAN verifica la firma RS256 del ID token con JWKS, issuer, audience, expiración, nonce y el scope `chatgpt.tokens.use.direct`. Los tokens quedan protegidos por permisos de administrador de Odoo; el cron renueva credenciales próximas a expirar.
4. **Inferencia**: DOLAN consulta `https://api.openai.com/v1/models` y realiza inferencia en `https://api.openai.com/v1/responses`, con bearer OAuth, `store=false`, `stream=true` y espera el evento `response.completed`. Las funciones del agente se convierten al formato de tools de Responses API.
5. **Prueba explícita**: La acción «Probar conexión con ChatGPT» consulta el catálogo habilitado y realiza una respuesta real; si el proveedor usa el motor local de respaldo, la prueba falla y el chat lo identifica como respaldo.

El flujo de plan ChatGPT de OpenAI está documentado para apps open source y alojadas localmente. Para una oferta comercial o una app remota multiusuario, OpenAI indica que puede requerirse aprobación. El modo OpenAI API con API key es alternativo y se factura por separado del plan ChatGPT; Ollama continúa disponible como proveedor local.

#### B. Integración con los modelos de IA de Odoo 20
La integración sigue los modelos y vistas disponibles en Odoo 20:
- `ai.agent`: Incluye los 3 agentes preconfigurados extraídos de la demo (*Odoo AI*, *Audit Reviewer*, *Auditor*) con sus `system_prompt` originales y soporte para agentes personalizados.
- `ai.skill`: Incluye las 12 habilidades nativas detectadas en la demo (*Shape View*, *Search Database*, *Update Records*, *Create Records*, *Generate Image*, *Web Search*, *Accounting Report Analysis*, *Accounting*, *Accounting Audit Evidence*, *Self Update*, *Build Automation*, *Create Lead (Livechat)*) mapeadas a llamadas `tools` (Function Calling) de ChatGPT sobre el ORM de Odoo respetando `ir.model.access` e `ir.rule` del usuario activo.
- `ai.composer` y `ai.prompt.button`: Las 14 reglas de interfaz (`mail_composer`, `chatter_ai_button`, `systray_ai_button`, `html_field_text_select`, `media_dialog`, etc.) y los 35 botones rápidos preconfigurados en español argentino.
- `ai.session` y `ai.session.event`: Historial de conversación integrado como pestaña `ai-chat` en el módulo `mail` (Conversaciones / Discuss) y en la barra superior (Systray).

---

### 3.2 `DOLAN_l10n_ar_afip`: Facturación Electrónica Argentina (ARCA / AFIP)

En Odoo 20 CE ya vienen incluidos con licencia `LGPL-3` (desarrollados por **ADHOC SA** y Odoo S.A.):
- `l10n_latam_invoice_document` (Tipos de comprobantes: Factura A, B, C, E, MiPyME FCE, Notas de Crédito/Débito).
- `l10n_latam_check` (Gestión de cheques propios, de terceros y Echeq).
- `l10n_ar` (Plan de cuentas argentino, tipos de responsabilidad ARCA, impuestos IVA/IIBB/Percepciones, actividades ARCA).
- `l10n_ar_withholding` (Retenciones de Ganancias e IIBB en pagos, escalas `l10n_ar.earnings.scale`).
- `l10n_ar_pos` y `l10n_ar_stock`.
- `certificate` (Gestión de certificados X.509 `certificate.certificate` y claves privadas `certificate.key`).

El módulo **`DOLAN_l10n_ar_afip`**, tomando como referencia la arquitectura open-source de **ADHOC (`ingadhoc/odoo-argentina-ce`)**, implementa funcionalidades de localización argentina:
1. **Modelos compatibles 1:1 con Odoo 20**:
   - `l10n_ar.afipws.connection`: Gestión de tickets de acceso TA (`token`, `sign`, `generation_time`, `expiration_time`, `l10n_ar_afip_ws`) contra WSAA (Homologación y Producción) usando `certificate.certificate` y `certificate.key` por empresa (`company_id`).
   - `l10n_ar_afip.ws.consult`: Asistente para consultar comprobantes emitidos y último número autorizado en ARCA (`FECompConsultar` / `FECompUltimoAutorizado`).
2. **Webservices ARCA / AFIP soportados**:
   - `wsfe` (Factura Electrónica Mercado Interno - RG 4291).
   - `wsfex` (Factura Electrónica de Exportación).
   - `wsmtxca` (Factura Electrónica con detalle de artículos).
   - `ws_sr_constancia_inscripcion` / `ws_sr_padron_a13` (Autocompletado de razón social, domicilio, condición de IVA y actividades al ingresar el CUIT de un cliente/proveedor).
3. **Impresión y Reportes Fiscales (`l10n_ar_reports` CE)**:
   - Código QR oficial de AFIP/ARCA en el PDF de la factura con JSON codificado en Base64.
   - Leyendas obligatorias (Régimen de Transparencia Fiscal al Consumidor Ley 27.743 / Monotributo / FCE MiPyME CBU).
   - Exportador de **Libro IVA Digital** (archivos TXT de Compras, Ventas y Alícuotas para importar en portal ARCA) y **SICORE**.

---

### 3.3 Autoinstalador Escalable y Multi-Empresa (`dolan-installer`)

Construiremos un instalador automatizado reproducible (Docker Compose para producción Linux/VPS + script nativo PowerShell/Bash para desarrollo) que:
1. **Descarga automática desde fuentes oficiales y nuestro repositorio**:
   - Clona con `git clone --depth 1 -b 20.0` (o rama objetivo) `odoo/odoo` (CE), los repositorios complementarios de **ADHOC / OCA** y nuestro repositorio privado/público `dolan-addons`.
2. **Preconfiguración por defecto `es_AR` / Multi-Empresa**:
   - Al inicializar una base de datos nueva, ejecuta un hook post-init (`DOLAN_setup_ar`) que:
     - Instala idioma Español (Argentina / Latinoamérica `es_AR` / `es_419`).
     - Configura país `Argentina`, moneda `ARS` activa, zona horaria `America/Argentina/Buenos_Aires`.
     - Carga el plan de cuentas argentino (`l10n_ar`), tipos de documentos LATAM y diarios de cheques/retenciones.
     - Habilita soporte Multi-Empresa preconfigurado para crear nuevas razones sociales (CUITs independientes con sus propios certificados ARCA y puntos de venta) en un asistente guiado.
3. **Selector de Perfiles de Cliente (Perfiles `DOLAN_*`)**:
   - Permite elegir en el instalador (vía CLI interactivo o variables `.env`) qué paquete instalar según el cliente:
     - `core_ar`: Base CE + Estética Enterprise + Facturación ARCA + Contabilidad Pro + IA ChatGPT.
     - `comercio_pos`: `core_ar` + Punto de Venta Pro / Restaurante / Código de Barras.
     - `industria_mrp`: `core_ar` + Manufactura Shop Floor + Calidad + Mantenimiento.
     - `servicios_sub`: `core_ar` + Suscripciones + Alquileres + Proyectos Gantt + Conocimiento.
     - `full`: Todos los módulos `DOLAN_*` seleccionados y sus dependencias compatibles.
