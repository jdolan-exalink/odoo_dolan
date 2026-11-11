# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models


def uninstall_hook(env):
    env['ir.ui.view']._dolan_unregister_generic_views()
