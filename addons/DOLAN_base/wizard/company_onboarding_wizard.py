from odoo import api, fields, models


class DolanCompanyOnboardingWizard(models.TransientModel):
    _name = "dolan.company.onboarding.wizard"
    _description = "Asistente de Alta Rápida Multi-Empresa Argentina (ARCA/AFIP)"

    name = fields.Char(string="Razón Social", required=True)
    cuit = fields.Char(string="CUIT (11 dígitos)", required=True, help="Ej: 30-71234567-9 o 30712345679")
    afip_responsibility_type_id = fields.Many2one(
        comodel_name="l10n_ar.afip.responsibility.type",
        string="Condición frente a ARCA (IVA)",
        required=True,
    )
    pos_number = fields.Integer(string="Punto de Venta ARCA por Defecto", default=1, required=True)
    street = fields.Char(string="Domicilio Fiscal")
    city = fields.Char(string="Localidad", default="CABA")
    zip_code = fields.Char(string="Código Postal")
    state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Provincia",
        domain="[('country_id.code', '=', 'AR')]",
    )
    email = fields.Char(string="Correo Electrónico")
    phone = fields.Char(string="Teléfono")
    env_type = fields.Selection(
        selection=[
            ("testing", "Homologación (Testing)"),
            ("production", "Producción"),
        ],
        string="Entorno ARCA / AFIP",
        default="testing",
        required=True,
    )
    grant_current_user = fields.Boolean(
        string="Habilitar acceso al usuario actual",
        default=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        resp_ri = self.env["l10n_ar.afip.responsibility.type"].search(
            [("name", "ilike", "Responsable Inscripto")], limit=1
        )
        if resp_ri and "afip_responsibility_type_id" in fields_list:
            res["afip_responsibility_type_id"] = resp_ri.id
        return res

    def action_create_argentine_company(self):
        """Crea la nueva empresa configurada para Argentina y sus diarios básicos."""
        self.ensure_one()
        ar_country = self.env.ref("base.ar", raise_if_not_found=False)
        ars_currency = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "ARS")], limit=1
        )
        if ars_currency and not ars_currency.active:
            ars_currency.sudo().active = True

        company_vals = {
            "name": self.name,
            "country_id": ar_country.id if ar_country else False,
            "currency_id": ars_currency.id if ars_currency else self.env.company.currency_id.id,
            "street": self.street,
            "city": self.city,
            "zip": self.zip_code,
            "state_id": self.state_id.id if self.state_id else False,
            "email": self.email,
            "phone": self.phone,
        }
        company = self.env["res.company"].sudo().create(company_vals)

        # Configurar CUIT y responsabilidad ARCA en el partner de la compañía
        cuit_latam_type = False
        if "l10n_latam.identification.type" in self.env.registry.models:
            cuit_latam_type = self.env["l10n_latam.identification.type"].search(
                [("name", "=", "CUIT")], limit=1
            )
        partner_vals = {
            "vat": self.cuit.replace("-", "").strip(),
            "l10n_ar_afip_responsibility_type_id": self.afip_responsibility_type_id.id,
        }
        if cuit_latam_type:
            partner_vals["l10n_latam_identification_type_id"] = cuit_latam_type.id
        company.partner_id.sudo().write(partner_vals)

        if "l10n_ar_afip_ws_environment" in company._fields:
            company.sudo().write({"l10n_ar_afip_ws_environment": self.env_type})

        if self.grant_current_user:
            self.env.user.sudo().write({"company_ids": [(4, company.id)]})

        return {
            "type": "ir.actions.act_window",
            "name": "Empresa Argentina Creada",
            "res_model": "res.company",
            "res_id": company.id,
            "view_mode": "form",
            "target": "current",
        }
