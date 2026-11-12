from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .icon_styles import ICON_STYLE_CHOICES


class DolanScreenPreference(models.Model):
    _name = "dolan.screen.preference"
    _description = "Preferencias personales de pantalla"
    _rec_name = "user_id"

    user_id = fields.Many2one(
        "res.users", string="Usuario", required=True, default=lambda self: self.env.user,
        index=True, ondelete="cascade",
    )
    theme_mode = fields.Selection(
        [("global", "Usar configuración general"), ("light", "Claro"), ("dark", "Oscuro"), ("system", "Automático (sistema)"), ("contrast", "Alto contraste")],
        string="Tema", required=True, default="global",
    )
    appearance_profile = fields.Selection(
        [("global", "Usar perfil global"),
         ("odoo_classic", "Enterprise Classic"),
         ("dolan_fluent", "Fluent"),
         ("dolan_liquid", "Liquid"),
         ("dolan_material", "Material"),
         ("dolan_minimal", "Minimal"),
         # Stored for compatibility during the incremental preference migration.
         ("legacy", "Conservar apariencia anterior"),
         ("enterprise_classic", "Clásico (anterior)"), ("graphite", "Graphite (anterior)"),
         ("glass", "Glass (anterior)"), ("minimal", "Minimal (anterior)"),
         ("liquid_glass_dark", "Liquid Glass oscuro (anterior)"),
         ("liquid_glass_light", "Liquid Glass claro (anterior)")],
        string="Perfil visual", required=True, default="global",
    )
    icon_style = fields.Selection(
        [("global", "Usar estilo global"), *ICON_STYLE_CHOICES],
        string="Estilo de iconos", required=True, default="global",
        help="La preferencia personal solo se aplica si el administrador habilitó la personalización individual.",
    )
    allow_user_icon_style = fields.Boolean(compute="_compute_allow_user_icon_style")
    allow_user_appearance = fields.Boolean(compute="_compute_allow_user_appearance")
    compact_mode = fields.Boolean(string="Densidad compacta", default=False)
    icon_scale = fields.Selection(
        [("global", "Usar tamaño global"), ("compact", "Compacto"), ("normal", "Normal"), ("large", "Grande")],
        string="Tamaño de iconos", required=True, default="global",
    )
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

    def _compute_allow_user_icon_style(self):
        allowed = self.env["ir.config_parameter"].sudo().get_param(
            "dolan_ui.allow_user_icon_style", "False"
        ).lower() in ("1", "true", "yes")
        for record in self:
            record.allow_user_icon_style = allowed

    def _compute_allow_user_appearance(self):
        allowed = self.env["ir.config_parameter"].sudo().get_param(
            "dolan_ui.allow_personal_appearance", "True"
        ).lower() in ("1", "true", "yes")
        for record in self:
            record.allow_user_appearance = allowed

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
                allowed = self.env["ir.config_parameter"].sudo().get_param(
                    "dolan_ui.allow_user_icon_style", "False"
                ).lower() in ("1", "true", "yes")
                if vals.get("icon_style", "global") != "global" and not allowed:
                    raise AccessError("El administrador no habilitó la personalización individual de iconos.")
                appearance_allowed = self.env["ir.config_parameter"].sudo().get_param(
                    "dolan_ui.allow_personal_appearance", "True"
                ).lower() in ("1", "true", "yes")
                if not appearance_allowed and any(key in vals for key in ("theme_mode", "compact_mode", "appearance_profile", "icon_scale")):
                    raise AccessError("El administrador no habilitó la personalización personal de la apariencia.")
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.user.has_group("base.group_system"):
            if any(record.user_id.id != self.env.uid for record in self):
                raise AccessError("Solo podés modificar tus propias preferencias de pantalla.")
            if vals.get("user_id", self.env.uid) != self.env.uid:
                raise AccessError("No podés cambiar el propietario de estas preferencias.")
            allowed = self.env["ir.config_parameter"].sudo().get_param(
                "dolan_ui.allow_user_icon_style", "False"
            ).lower() in ("1", "true", "yes")
            if "icon_style" in vals and not allowed and vals["icon_style"] != "global":
                raise AccessError("El administrador no habilitó la personalización individual de iconos.")
            appearance_allowed = self.env["ir.config_parameter"].sudo().get_param(
                "dolan_ui.allow_personal_appearance", "True"
            ).lower() in ("1", "true", "yes")
            if not appearance_allowed and any(key in vals for key in ("theme_mode", "compact_mode", "appearance_profile", "icon_scale")):
                raise AccessError("El administrador no habilitó la personalización personal de la apariencia.")
        return super().write(vals)

    @api.model
    def current_user_preferences(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if not preference:
            preference = self.create({"user_id": self.env.uid})
        return preference

    def action_dolan_add_personal_folder(self):
        self.ensure_one()
        desktop = self.env["dolan.desktop.preference"].current_user()
        placed = desktop.dolan_add_personal_folder()
        if placed:
            message = _("La carpeta Personal ya está en tu Inicio con %s aplicaciones.", placed)
        else:
            message = _("No tenés aplicaciones de Personal instaladas o habilitadas para tu usuario.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Escritorio"), "message": message,
                       "type": "success" if placed else "warning", "sticky": False},
        }

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
