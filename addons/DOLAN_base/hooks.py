import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Inicializa configuración por defecto para Argentina (es_AR, ARS, Plan Contable ar_ri) y limpia promociones OEEL-1."""
    _logger.info("DOLAN_base: Ejecutando post_init_hook de configuración Argentina (es_AR) y limpieza CE...")

    # 1. Ocultar módulos promocionales OEEL-1 del tablero de Aplicaciones
    env.cr.execute(
        """
        UPDATE ir_module_module
           SET application = FALSE
         WHERE license = 'OEEL-1'
           AND application = TRUE
        """
    )

    # 2. Mantener Español (Argentina) como único idioma español visible.
    # es_419 cargaba etiquetas genéricas y dejaba sin traducir apps que sí
    # tienen traducción específica para Argentina.
    languages = env["res.lang"].with_context(active_test=False)
    argentina = languages.search([("code", "=", "es_AR")], limit=1)
    if argentina and not argentina.active:
        argentina.write({"active": True})
    latin_american = languages.search([("code", "=", "es_419")], limit=1)
    if latin_american and latin_american.active:
        latin_american.write({"active": False})
    try:
        # Keep the technical superuser in the framework's source language.
        # Native tests and service diagnostics must not inherit human UI defaults.
        root = env.ref("base.user_root")
        root.write({"lang": "en_US"})
        human_users = env["res.users"].search([
            ("share", "=", False), ("id", "!=", root.id),
        ])
        human_users.write({"lang": "es_AR", "tz": "America/Argentina/Buenos_Aires"})
        env["ir.default"].sudo().set("res.users", "lang", "es_AR")
        env["ir.default"].sudo().set("res.partner", "lang", "es_AR")
    except Exception as exc:
        _logger.warning("DOLAN_base: No se pudo fijar idioma es_AR por defecto: %s", exc)

    # 3. Activar moneda ARS (Peso Argentino)
    ars = env["res.currency"].with_context(active_test=False).search([("name", "=", "ARS")], limit=1)
    if ars and not ars.active:
        ars.active = True

    # 4. Configurar país Argentina y moneda ARS en la compañía principal
    ar_country = env.ref("base.ar", raise_if_not_found=False)
    main_company = env.ref("base.main_company", raise_if_not_found=False)
    ri = env.ref("l10n_ar.res_IVARI", raise_if_not_found=False)
    if main_company and ar_country:
        vals = {"country_id": ar_country.id}
        if ars:
            vals["currency_id"] = ars.id
        if ri and "l10n_ar_afip_responsibility_type_id" in main_company._fields:
            vals["l10n_ar_afip_responsibility_type_id"] = ri.id
        try:
            main_company.write(vals)
        except Exception as exc:
            _logger.warning("DOLAN_base: No se pudo actualizar moneda/país de main_company: %s", exc)

    # 5. Access is assigned by explicit business roles, never to all internal users.
    # Installing or upgrading the base suite must not grant accounting privileges.

    # 6. Parámetros de sistema seguros por defecto
    icp = env["ir.config_parameter"].sudo()
    icp.set_str("l10n_ar_fiscal_ws.env_type", icp.get_str("l10n_ar_fiscal_ws.env_type", "homologation"))
    icp.set_str("database.expiration_date", "2099-12-31 23:59:59")
    icp.set_str("database.expiration_reason", "self_hosted_ce")
    _logger.info("DOLAN_base: Configuración inicial Argentina (es_AR) completada.")
