# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Enable an isolated USD pricelist for each Argentine operating company."""
    usd = env.ref('base.USD', raise_if_not_found=False)
    argentina = env.ref('base.ar', raise_if_not_found=False)
    if not usd or not argentina:
        return
    usd.active = True
    companies = env['res.company'].sudo().search([
        ('active', '=', True),
        ('vat', '!=', False),
    ]).filtered(lambda company: company.country_id == argentina)
    Pricelist = env['product.pricelist'].sudo()
    for company in companies:
        existing = Pricelist.search([
            ('company_id', '=', company.id),
            ('currency_id', '=', usd.id),
        ], limit=1)
        if not existing:
            Pricelist.create({
                'name': 'Default USD - %s' % company.display_name,
                'currency_id': usd.id,
                'company_id': company.id,
            })
