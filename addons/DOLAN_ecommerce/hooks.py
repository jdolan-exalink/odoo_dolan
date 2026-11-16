def post_init_hook(env):
    """El sitio que crea Odoo queda en la primera empresa de la base; si el usuario público del sitio no
    pertenece a esa empresa, toda página pública (incluido /web/login) da «Acceso a empresas sin autorización».
    Se pasa el sitio a la empresa del usuario público."""
    for website in env['website'].sudo().search([]):
        public = website.user_id
        if public and website.company_id not in public.company_ids:
            website.company_id = public.company_id
