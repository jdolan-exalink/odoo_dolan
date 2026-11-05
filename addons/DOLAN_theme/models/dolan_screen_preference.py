from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DolanScreenPreference(models.Model):
    _name = "dolan.screen.preference"
    _description = "Preferencias personales de pantalla DOLAN"
    _rec_name = "user_id"

    user_id = fields.Many2one(
        "res.users", string="Usuario", required=True, default=lambda self: self.env.user,
        index=True, ondelete="cascade",
    )
    theme_mode = fields.Selection(
        [("light", "Claro"), ("dark", "Oscuro")],
        string="Tema", required=True, default="light",
    )
    compact_mode = fields.Boolean(string="Densidad compacta", default=False)
    company_id = fields.Many2one(
        "res.company", string="Empresa para el estilo", required=True,
        default=lambda self: self.env.company,
    )
    primary_color = fields.Char(related="company_id.dolan_primary_color", readonly=False)
    secondary_color = fields.Char(related="company_id.dolan_secondary_color", readonly=False)
    home_bg_style = fields.Selection(related="company_id.dolan_home_bg_style", readonly=False)
    full_width_sheets = fields.Boolean(related="company_id.dolan_full_width_sheets", readonly=False)
    hidden_app_menu_ids = fields.Many2many(
        "ir.ui.menu", "dolan_screen_preference_hidden_menu_rel",
        "preference_id", "menu_id", string="Aplicaciones ocultas",
        domain=[("parent_id", "=", False)],
        help="Solo oculta las tarjetas del menú de inicio para tu usuario. No desinstala módulos ni modifica permisos.",
    )

    _user_unique = models.Constraint(
        "UNIQUE(user_id)", "Ya existe una configuración de pantalla para este usuario.",
    )

    @api.constrains("hidden_app_menu_ids")
    def _check_settings_app_visible(self):
        protected_menu = self.env.ref("base.menu_administration", raise_if_not_found=False)
        if protected_menu and any(protected_menu in record.hidden_app_menu_ids for record in self):
            raise ValidationError("No se puede ocultar Ajustes porque contiene esta configuración de pantalla.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.user.has_group("base.group_system"):
                vals["user_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.user.has_group("base.group_system"):
            if any(record.user_id.id != self.env.uid for record in self):
                raise AccessError("Solo podés modificar tus propias preferencias de pantalla.")
            if vals.get("user_id", self.env.uid) != self.env.uid:
                raise AccessError("No podés cambiar el propietario de estas preferencias.")
        return super().write(vals)

    @api.model
    def current_user_preferences(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if not preference:
            preference = self.create({"user_id": self.env.uid})
        return preference

    @api.model
    def action_open_current_user(self):
        preference = self.current_user_preferences()
        return {
            "type": "ir.actions.act_window",
            "name": "Configuración de pantalla",
            "res_model": self._name,
            "res_id": preference.id,
            "view_mode": "form",
            "views": [(self.env.ref("DOLAN_theme.view_dolan_screen_preference_form").id, "form")],
            "target": "current",
        }
