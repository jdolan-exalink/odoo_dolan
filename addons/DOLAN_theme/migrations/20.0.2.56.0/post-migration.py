from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    launcher = env.ref("DOLAN_theme.action_dolan_home", raise_if_not_found=False)
    if not launcher:
        return
    users = env["res.users"].sudo().with_context(active_test=False).search([
        ("share", "=", False),
    ])
    users.write({"action_id": launcher.id})
