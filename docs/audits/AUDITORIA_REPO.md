# Auditoría del repositorio — E0 del PRD maestro v1.1

Fecha: 13/11/2026. Alcance: inventario del árbol, manifiestos, menús, permisos, tests, instalador y CI, más la
línea base del catálogo visual (E1). Matriz de detalle: [MATRIZ_COBERTURA.csv](MATRIZ_COBERTURA.csv).

## Commit auditado

| Qué | SHA |
|---|---|
| `main` congelado (merge PR #47) | `00fabb7d7d5e08c1bf2a7f5af2dfba210771153b` |
| Base de esta rama (main + PR #49, carpeta Personal) | `bba6bab4d090b079b3adadfd17678937409c2881` |

Árbol de `main`: 1.199 archivos (1.062 en `addons/`, 42 en `docs/`, 36 en `scripts/`, 32 en `installer/`).

## Cómo se hizo

* `scripts/audit_inventory.py`: lee cada `__manifest__.py` y cuenta modelos nuevos y heredados, vistas,
  controladores, JS, SVG, filas de `security/ir.access.csv` (y cuántas tienen dominio), menús raíz, acciones,
  grupos, archivos y funciones de test y migraciones. Se puede volver a correr en cualquier commit.
* Validadores de la CI corridos localmente: `validate_addons.py` (0 errores), `test_theme_asset_bootstrap.py`,
  `test_install_profile_addons.py`, `test_installer_locale_es_ar.py`, `distribution_lock.py` y `compileall`: todos OK.
  Los tests Go del instalador no se corrieron (no hay Go en la PC de desarrollo).
* Menús raíz y módulos instalados leídos (solo lectura) de la base local `dolan_real_copy_20261029`.
* Búsquedas de código por capacidad (CAEA, FCE, WSFEX, SICORE, SIRCREB, SIRTAC, padrones, eCheq, arqueo, Clover,
  F.931, LSD, opt-out, auditoría, sucursal). Una búsqueda sin resultados se registra como NO-VERIFICADO,
  nunca como ausente.
* Pruebas de instalación en dos bases descartables: una limpia (`dolan_catalog_test`) y una copia de la base local
  (`dolan_catalog_clone_20261113`, con cron apagado para no disparar ARCA, WAHA ni Mercado Pago).

Ningún estado se subió por un mensaje de commit: IMPLEMENTADO-PENDIENTE-QA significa que hay código y tests propios,
no que pasó QA funcional.

## Inventario de módulos

41 módulos con manifiesto (40 en `main` + `DOLAN_app_catalog` nuevo), todos LGPL-3. 475 funciones de test Python.

| Grupo | Módulos | Observaciones |
|---|---|---|
| Base y UI | DOLAN_base, DOLAN_theme, DOLAN_views, DOLAN_app_catalog | El theme tiene 10 migraciones y es dueño de las carpetas del Escritorio. |
| Fiscal y contable | DOLAN_l10n_ar_afip (14 modelos, 116 tests), DOLAN_accounting (17 modelos, 59 tests), DOLAN_account_reports, DOLAN_bank_ar, DOLAN_collections, DOLAN_exchange, DOLAN_l10n_ar_cot | CAEA, FCE y WSFEX tienen código; solo A/B/C está validado en producción. |
| Comercio y POS | DOLAN_pos, DOLAN_payment_terminal, DOLAN_discount_engine, DOLAN_pricelist, DOLAN_credit_limit, DOLAN_credit_limit_pos, DOLAN_marketplace, ePOS_print, pos_scale_management | DOLAN_payment_terminal y ePOS_print no tienen tests. |
| Personal | DOLAN_hr_core, _leave, _scheduling, _attendance, _overtime, _payroll_bridge, _portal, _portal_payroll, _documents, _talent, _reports, DOLAN_payroll_ar, paquetes DOLAN_personal_operativo y DOLAN_personal | Todos con tests salvo los dos paquetes (solo dependencias). |
| Operaciones y servicios | DOLAN_stock_mrp, DOLAN_subscription, DOLAN_renting | |
| IA y comunicación | DOLAN_ai (82 tests), DOLAN_ocr, DOLAN_whatsapp, DOLAN_knowledge_bi | |

El README dice 16 módulos DOLAN_* más 2; el árbol real tiene 38 DOLAN_* más ePOS_print y pos_scale_management.
El instalador (`installer/internal/packages/catalog.go`) tiene una entrada por módulo, pero varias versiones
están desactualizadas (por ejemplo DOLAN_theme figura 20.0.2.51.0 y el manifiesto dice 20.0.2.80.0) y algunas
dependencias no coinciden con el manifiesto (DOLAN_pos no lista pos_scale_management; DOLAN_l10n_ar_afip no lista
l10n_ar_withholding).

## Hallazgos

1. **Permisos y multiempresa.** Odoo 20 reemplazó `ir.model.access` + `ir.rule` por `security/ir.access.csv` con
   dominio. No hay registros `ir.rule` en ningún módulo DOLAN; el aislamiento depende de los dominios de esas filas
   (por ejemplo 36 de 48 en DOLAN_discount_engine, 10 de 49 en DOLAN_accounting). Revisar en E2 que todos los
   modelos con `company_id` tengan dominio por empresa, y probar con dos empresas.
2. **Perfiles del instalador.** El perfil Completo incluye la Suite Personal (DOLAN_personal), pero no
   DOLAN_bank_ar, DOLAN_collections ni DOLAN_l10n_ar_cot. Básico y Servicios no incluyen DOLAN_discount_engine. Si es
   intencional, conviene documentarlo; si no, corregirlo junto con el PR #40 (actualizador de perfiles).
3. **Crédito.** La migración 20.0.1.0.2 de DOLAN_credit_limit corrió sin errores al actualizar la copia de la base
   local. Falta la prueba funcional de bloqueo `dolan_credit_hold` y la excepción en POS.
4. **Catálogo de íconos del theme.** Varios xmlids del catálogo de íconos no existen en la base (por ejemplo
   `DOLAN_payment_terminal.menu_payment_terminal_root`, el real es `menu_terminal_root`); hoy funcionan por alias
   de nombre. Sin impacto, pero frágil.
5. **Documentación por módulo.** 34 de 41 módulos no tienen README propio.
6. **Base local.** La base `dolan_real_copy_20261029` tiene DOLAN_l10n_ar_afip 20.0.1.45.0 (cambios sin commitear
   del PR #46) y DOLAN_payroll_ar 20.0.1.1.0, mientras `main` tiene 1.44.0 y 1.2.0. Para probar ramas sobre una
   copia hay que actualizar esos módulos primero.
7. **Capacidades sin implementación propia** (detalle en la matriz): caja central y arqueo (F08), bitácora de
   auditoría (F15), sucursales dentro de una empresa (F14), ficha 360° de cuenta corriente (F06), rutas y
   prueba de entrega (F22). Son las que el catálogo muestra como En desarrollo o Planificado.

## E1: catálogo de apps

* `DOLAN_app_catalog` depende de base, web y DOLAN_theme (es el dueño de las carpetas; está en todos los perfiles).
  El theme no depende del catálogo: no hay dependencia circular.
* Fuente versionada: `addons/DOLAN_app_catalog/data/app_catalog.json` (94 apps, 11 carpetas). El importador
  `_sync_catalog` es idempotente y no pisa lo que decide el administrador (ocultar, orden propio).
* Estado en tiempo de ejecución: si el menú raíz real existe, la app abre directo y el ícono del catálogo se apaga;
  si existe la acción real y su módulo está instalado, el ícono abre esa acción con sus grupos; si el módulo está en
  el addons path sin instalar, muestra «Disponible para instalar»; si no hay implementación, muestra la pantalla
  informativa «En desarrollo» o «Planificado», sin botones de operaciones. El servidor valida en
  `get_placeholder` que el usuario pueda ver el menú. Nunca instala módulos.
* Carpetas: adaptador sobre `dolan.desktop.preference` del theme. Ubica una sola vez cada ícono del catálogo en la
  carpeta del usuario con ese nombre (reutiliza «Personal» y «Configuraciones»); si el usuario lo mueve o borra la
  carpeta, no vuelve. Las apps reales sueltas solo se mueven si el usuario lo pide
  (Catálogo de apps → Opciones → Ordenar mi Escritorio por carpetas).
* Íconos: 56 glifos propios (`scripts/app_catalog_glyphs.py`, licencia del proyecto) generados en las cinco
  familias del theme por `scripts/build_app_catalog.py`, que también actualiza `dolan_icon_catalog.json` e
  `icon_asset_manifest.json`. Las apps que ya tenían ícono lo reutilizan. La CI corre `build_app_catalog.py --check`.
* Tests: 15 tests propios (idempotencia, decisiones del administrador, no duplicar apps reales, accesos directos con
  grupos, visibilidad, perfiles, ubicación en carpetas sin pisar al usuario, re-sincronización al instalar módulos).
  Se ajustó un test de DOLAN_theme para que ignore las carpetas que agrega el catálogo.

## Rollback

Desinstalar `DOLAN_app_catalog` desde Aplicaciones (o con `button_immediate_uninstall` en `odoo-bin shell`)
borra sus menús, acciones, registros y datos XML; probado en la base descartable `dolan_catalog_test`
(0 registros del módulo después de desinstalar). No toca las apps reales ni su ubicación en el Escritorio.
Para volver atrás los íconos del theme basta con revertir el commit (son archivos estáticos).

Las carpetas que el catálogo creó en cada Escritorio quedan; el usuario las puede borrar desde el Escritorio.
Antes de instalar en una base con datos: backup de base y filestore (ver `docs/admin`).
