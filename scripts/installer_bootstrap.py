"""One-shot Odoo shell bootstrap used by the interactive installer."""
import json


with open("/tmp/dolan-installer.json", encoding="utf-8") as config_file:
    config = json.load(config_file)

company = env.company.sudo()
partner = company.partner_id.sudo()
responsibility_model = env["l10n_ar.afip.responsibility.type"].sudo()
responsibility_name = config["responsibility"]
search_terms = [responsibility_name]
if "monotribut" in responsibility_name.lower():
    search_terms.append("Monotribut")
responsibility = False
for search_term in search_terms:
    responsibility = responsibility_model.search([("name", "ilike", search_term)], limit=1)
    if responsibility:
        break
if not responsibility:
    raise RuntimeError("No se encontró la responsabilidad ARCA: %s" % responsibility_name)

company.write({
    "name": config["company_name"],
    "country_id": env.ref("base.ar").id,
})
partner_values = {
    "name": config["company_name"],
    "vat": "".join(ch for ch in config["cuit"] if ch.isdigit()),
    "street": config["address"],
    "city": config.get("city") or False,
    "l10n_ar_afip_responsibility_type_id": responsibility.id,
}
try:
    identification_model = env["l10n_latam.identification.type"].sudo()
except KeyError:
    # Some localization combinations do not install this optional model.
    identification_model = False
if identification_model:
    identification_type = identification_model.search([("name", "=", "CUIT")], limit=1)
    if identification_type and "l10n_latam_identification_type_id" in partner._fields:
        partner_values["l10n_latam_identification_type_id"] = identification_type.id
partner.write(partner_values)

admin = env.ref("base.user_admin").sudo()
admin.write({
    "name": config.get("admin_name") or config["admin_email"],
    "login": config["admin_email"],
    "email": config["admin_email"],
    "password": config["admin_password"],
    "lang": "es_AR",
    "tz": "America/Argentina/Buenos_Aires",
})

journals = env["account.journal"].sudo().search(
    [("company_id", "=", company.id), ("type", "=", "sale"), ("active", "=", True)],
    order="sequence, id",
)
if journals and "l10n_ar_afip_pos_number" in journals._fields:
    invoice_journal = journals[0]
    journal_values = {"l10n_ar_afip_pos_number": int(config["billing_pos"])}
    if "l10n_ar_afip_pos_system" in journals._fields:
        journal_values["l10n_ar_afip_pos_system"] = "DOLAN_WSFE"
    invoice_journal.write(journal_values)

    if "pos.config" in env.registry.models:
        pos_model = env["pos.config"].sudo()
        pos_configs = pos_model.search([("company_id", "=", company.id)])
        pos_journal = env["account.journal"].sudo().search([
            ("company_id", "=", company.id), ("type", "=", "sale"),
            ("l10n_ar_afip_pos_number", "=", int(config["pos_pos"])),
        ], limit=1)
        if not pos_journal:
            pos_journal = env["account.journal"].sudo().search([
                ("company_id", "=", company.id), ("type", "=", "sale"), ("code", "=", "POS")
            ], limit=1)
        if not pos_journal:
            vals = {
                "name": "Ventas Punto de Venta",
                "type": "sale",
                "code": "POS",
                "company_id": company.id,
            }
            for field_name in ("default_account_id", "currency_id"):
                if field_name in invoice_journal._fields and invoice_journal[field_name]:
                    vals[field_name] = invoice_journal[field_name].id
            pos_journal = env["account.journal"].sudo().create(vals)
        journal_values = {"l10n_ar_afip_pos_number": int(config["pos_pos"])}
        if "l10n_ar_afip_pos_system" in pos_journal._fields:
            journal_values["l10n_ar_afip_pos_system"] = "DOLAN_WSFE"
        pos_journal.write(journal_values)

        if not pos_configs:
            pos_values = pos_model.default_get(list(pos_model._fields))
            pos_values.update({"name": "Punto de Venta", "company_id": company.id})
            if "picking_type_id" in pos_model._fields and not pos_values.get("picking_type_id"):
                warehouse = env["stock.warehouse"].sudo().search([("company_id", "=", company.id)], limit=1)
                picking_type = getattr(warehouse, "pos_type_id", False) or getattr(warehouse, "out_type_id", False)
                if picking_type:
                    pos_values["picking_type_id"] = picking_type.id
            pos_configs = pos_model.create(pos_values)

        pos_config = pos_configs[:1]
        for field_name in ("invoice_journal_id", "journal_id"):
            if field_name in pos_config._fields:
                pos_config.write({field_name: pos_journal.id})

env.cr.commit()
print("Empresa, administrador y punto de venta de facturación configurados.")
params = env["ir.config_parameter"].sudo()
params.set_param("dolan.installer.profile", config.get("profile", ""))
params.set_param("dolan.installer.modules", config.get("modules", ""))
env.cr.commit()
if "pos.config" not in env.registry.models:
    print("El perfil no incluye PoS; se guardó el PV indicado para cuando se habilite.")
