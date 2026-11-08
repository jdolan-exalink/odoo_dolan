from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        launcher = self.env.ref("DOLAN_theme.action_dolan_home", raise_if_not_found=False)
        if launcher:
            for vals in vals_list:
                if not vals.get("share") and "action_id" not in vals:
                    vals["action_id"] = launcher.id
        return super().create(vals_list)
