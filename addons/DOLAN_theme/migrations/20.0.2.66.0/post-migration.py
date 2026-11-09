from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    launcher = env.ref("DOLAN_theme.action_dolan_home", raise_if_not_found=False)
    if launcher and launcher.path != "home":
        launcher.write({"path": "home"})
