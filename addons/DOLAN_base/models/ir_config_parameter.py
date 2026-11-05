from odoo import api, models


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def get_param(self, key: str, default=False):
        """Shim de compatibilidad Odoo 20.0 para módulos que invocan get_param."""
        val = self.get_str(key, default="")
        if val == "":
            return default
        return val

    @api.model
    def set_param(self, key: str, value):
        """Shim de compatibilidad Odoo 20.0 para módulos que invocan set_param."""
        return self.set_str(key, value)
