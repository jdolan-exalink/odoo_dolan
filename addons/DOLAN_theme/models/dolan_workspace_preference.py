from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


WORKSPACE_ROLES = ("all", "administracion", "ventas", "compras", "deposito", "produccion", "mantenimiento")
WORKSPACE_KPI_KEYS = {
    "invoices_overdue", "bills_due_week", "invoices_draft", "quotes_expiring", "quotes_open",
    "sales_to_invoice", "po_pending", "receipts_pending", "pickings_late", "mrp_open",
    "maintenance_open", "my_activities",
}
WORKSPACE_SECTION_KEYS = {
    "pos", "quick_actions", "attention", "summary", "other_metrics", "activity",
}
WORKSPACE_ACTION_KEYS = {
    "new_invoice", "new_sale", "new_partner", "new_payment",
    "whatsapp", "libro_iva", "toggle_ai", "open_search",
}
WORKSPACE_WIDGET_SIZES = {"small", "medium", "large", "full"}


class DolanWorkspacePreference(models.Model):
    _name = "dolan.workspace.preference"
    _description = "Preferencias personales de Mi Espacio"
    _rec_name = "user_id"

    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, index=True, ondelete="cascade")
    role_filter = fields.Selection(
        [(key, "Todo" if key == "all" else key.replace("_", " ").title()) for key in WORKSPACE_ROLES],
        required=True, default="all",
    )
    visible_widget_keys = fields.Json(default=False, help="Vacío significa que se muestran todos los indicadores habilitados.")
    kpi_states = fields.Json(default=dict, help="Estados personales de posponer o marcar leído.")
    indicator_mode = fields.Selection(
        [("priorities", "Prioridades"), ("complete", "Completo"), ("custom", "Personalizado")],
        required=True, default="priorities",
    )
    visible_section_keys = fields.Json(default=False)
    workspace_order = fields.Json(default=False)
    workspace_sizes = fields.Json(default=dict)
    quick_action_keys = fields.Json(default=False)

    _user_unique = models.Constraint("UNIQUE(user_id)", "Ya existen preferencias de Mi Espacio para este usuario.")

    @api.model
    def current_user_preferences(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        return preference or self.create({"user_id": self.env.uid})

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group("base.group_system"):
            for vals in vals_list:
                vals["user_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.user.has_group("base.group_system"):
            if any(record.user_id.id != self.env.uid for record in self):
                raise AccessError("Solo podés modificar tus preferencias de Mi Espacio.")
            if vals.get("user_id", self.env.uid) != self.env.uid:
                raise AccessError("No podés cambiar el propietario de estas preferencias.")
        return super().write(vals)

    @api.constrains(
        "role_filter", "visible_widget_keys", "kpi_states", "indicator_mode",
        "visible_section_keys", "workspace_order", "workspace_sizes", "quick_action_keys",
    )
    def _check_personal_workspace_data(self):
        for record in self:
            if record.role_filter not in WORKSPACE_ROLES:
                raise ValidationError("El filtro de Mi Espacio no es válido.")
            visible = record.visible_widget_keys
            if visible not in (False, None) and (
                not isinstance(visible, list) or len(visible) > len(WORKSPACE_KPI_KEYS)
                or any(key not in WORKSPACE_KPI_KEYS for key in visible)
            ):
                raise ValidationError("La lista de indicadores de Mi Espacio no es válida.")
            states = record.kpi_states or {}
            if not isinstance(states, dict) or any(key not in WORKSPACE_KPI_KEYS for key in states):
                raise ValidationError("El estado de indicadores de Mi Espacio no es válido.")
            for state in states.values():
                if not isinstance(state, dict) or set(state) - {"dismissedCount", "snoozeUntil"}:
                    raise ValidationError("El estado de indicadores contiene valores no permitidos.")
                for name, value in state.items():
                    if not isinstance(value, (int, float)) or value < 0 or value > 4_102_444_800_000:
                        raise ValidationError("El estado de indicadores contiene un valor inválido.")
            sections = record.visible_section_keys
            if sections not in (False, None) and (
                not isinstance(sections, list) or len(sections) > len(WORKSPACE_SECTION_KEYS)
                or any(not isinstance(key, str) or key not in WORKSPACE_SECTION_KEYS for key in sections)
            ):
                raise ValidationError("La lista de secciones de Mi Espacio no es válida.")
            order = record.workspace_order
            if order not in (False, None) and (
                not isinstance(order, list)
                or any(not isinstance(key, str) or key not in WORKSPACE_SECTION_KEYS for key in order)
                or len(order) != len(set(order))
            ):
                raise ValidationError("El orden de Mi Espacio no es válido.")
            sizes = record.workspace_sizes or {}
            if not isinstance(sizes, dict) or any(
                key not in WORKSPACE_SECTION_KEYS or not isinstance(value, str)
                or value not in WORKSPACE_WIDGET_SIZES
                for key, value in sizes.items()
            ):
                raise ValidationError("Los tamaños de widgets de Mi Espacio no son válidos.")
            actions = record.quick_action_keys
            if actions not in (False, None) and (
                not isinstance(actions, list) or len(actions) > len(WORKSPACE_ACTION_KEYS)
                or any(not isinstance(key, str) or key not in WORKSPACE_ACTION_KEYS for key in actions)
            ):
                raise ValidationError("La lista de accesos rápidos no es válida.")
