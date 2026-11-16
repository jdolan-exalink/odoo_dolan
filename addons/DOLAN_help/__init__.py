from . import controllers
from . import models


def post_init_hook(env):
    """El ícono «Ayuda» del catálogo se apaga apenas existe el menú real."""
    env['dolan.app.catalog.entry'].sudo().search([])._apply_runtime_state()
