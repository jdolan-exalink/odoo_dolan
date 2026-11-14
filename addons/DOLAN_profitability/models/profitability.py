from odoo import fields, models, tools


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    dolan_unit_cost = fields.Float('Costo unitario al facturar', digits='Product Price', copy=False, readonly=True,
                                   help='Costo del producto (en la moneda de la empresa) en el momento de publicar la factura.')


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')):
            for line in move.invoice_line_ids.filtered(lambda l: l.product_id and not l.dolan_unit_cost):
                cost = line.product_id.with_company(move.company_id).standard_price
                if line.product_uom_id and line.product_uom_id != line.product_id.uom_id:
                    cost = line.product_id.uom_id._compute_price(cost, line.product_uom_id)
                line.sudo().dolan_unit_cost = cost
        return posted


class DolanProfitability(models.Model):
    """Una fila por línea de producto de factura o nota de crédito de cliente publicada."""
    _name = 'dolan.profitability'
    _description = 'Rentabilidad'
    _auto = False
    _order = 'date desc'

    date = fields.Date('Fecha', readonly=True)
    move_id = fields.Many2one('account.move', 'Comprobante', readonly=True)
    move_type = fields.Selection([('out_invoice', 'Factura'), ('out_refund', 'Nota de crédito')], 'Tipo', readonly=True)
    company_id = fields.Many2one('res.company', 'Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', 'Moneda', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Cliente', readonly=True)
    user_id = fields.Many2one('res.users', 'Vendedor', readonly=True)
    product_id = fields.Many2one('product.product', 'Producto', readonly=True)
    categ_id = fields.Many2one('product.category', 'Categoría', readonly=True)
    quantity = fields.Float('Cantidad', readonly=True)
    revenue = fields.Monetary('Ingreso neto', readonly=True)
    cost = fields.Monetary('Costo', readonly=True)
    margin = fields.Monetary('Margen', readonly=True)
    margin_pct = fields.Float('Margen (%)', readonly=True, aggregator=None, digits=(16, 2))
    cost_estimated = fields.Boolean('Costo estimado', readonly=True,
                                    help='La factura es anterior a la instalación: se usó el costo actual del producto.')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH lines AS (
                    SELECT aml.id,
                           aml.date,
                           aml.move_id,
                           move.move_type,
                           aml.company_id,
                           company.currency_id,
                           move.commercial_partner_id AS partner_id,
                           move.invoice_user_id AS user_id,
                           aml.product_id,
                           template.categ_id,
                           CASE WHEN move.move_type = 'out_refund' THEN -1 ELSE 1 END AS sign,
                           aml.quantity,
                           -aml.balance AS revenue,
                           COALESCE(NULLIF(aml.dolan_unit_cost, 0),
                                    (product.standard_price ->> aml.company_id::text)::numeric, 0) AS unit_cost,
                           COALESCE(aml.dolan_unit_cost, 0) = 0 AS cost_estimated
                      FROM account_move_line aml
                      JOIN account_move move ON move.id = aml.move_id
                      JOIN res_company company ON company.id = aml.company_id
                      JOIN product_product product ON product.id = aml.product_id
                      JOIN product_template template ON template.id = product.product_tmpl_id
                     WHERE move.state = 'posted'
                       AND move.move_type IN ('out_invoice', 'out_refund')
                       AND aml.display_type = 'product'
                )
                SELECT id, date, move_id, move_type, company_id, currency_id, partner_id, user_id, product_id, categ_id,
                       sign * quantity AS quantity,
                       revenue,
                       sign * quantity * unit_cost AS cost,
                       revenue - sign * quantity * unit_cost AS margin,
                       CASE WHEN revenue != 0 THEN (revenue - sign * quantity * unit_cost) / revenue * 100 ELSE 0 END AS margin_pct,
                       cost_estimated
                  FROM lines
            )
        """)
