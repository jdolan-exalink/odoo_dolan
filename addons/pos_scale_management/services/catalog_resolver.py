class CatalogResolver:
    """Resolve explicit product/category rules for one scale without cloning products."""

    def __init__(self, device):
        self.device = device

    def resolve(self):
        device = self.device
        rules = device.product_assignment_ids.filtered('active')
        included_products = rules.filtered(
            lambda line: line.assignment_type == 'product' and line.disposition == 'include'
        ).mapped('product_id')
        included_categories = rules.filtered(
            lambda line: line.assignment_type == 'category' and line.disposition == 'include'
        ).mapped('category_id')
        if included_categories:
            category_products = self.device.env['product.product'].search([
                ('product_tmpl_id.categ_id', 'child_of', included_categories.ids),
                ('active', '=', True), ('sale_ok', '=', True), ('product_tmpl_id.available_in_pos', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', device.company_id.id),
            ])
            included_products |= category_products

        excluded_products = rules.filtered(
            lambda line: line.assignment_type == 'product' and line.disposition == 'exclude'
        ).mapped('product_id')
        excluded_categories = rules.filtered(
            lambda line: line.assignment_type == 'category' and line.disposition == 'exclude'
        ).mapped('category_id')
        eligible = included_products.filtered(
            lambda product: product.active and product.sale_ok and product.product_tmpl_id.available_in_pos
            and (not product.company_id or product.company_id == device.company_id)
        )
        if excluded_categories:
            excluded_tree = self.device.env['product.category'].search([('id', 'child_of', excluded_categories.ids)])
            eligible = eligible.filtered(lambda product: product.product_tmpl_id.categ_id not in excluded_tree)
        return (eligible - excluded_products).sorted(lambda product: (product.display_name.lower(), product.id))
