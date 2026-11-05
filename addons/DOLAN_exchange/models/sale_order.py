# -*- coding: utf-8 -*-
from odoo import fields, models, _, Command
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dolan_exchange_rate = fields.Float(string='Cotización BNA Venta', digits=(16, 4), readonly=True, copy=False)
    dolan_exchange_rate_date = fields.Date(string='Fecha cotización BNA', readonly=True, copy=False)
    dolan_exchange_rate_source = fields.Char(string='Fuente del tipo de cambio', readonly=True, copy=False)
    dolan_exchange_rate_id = fields.Many2one('dolan.bna.exchange.rate', string='Registro BNA aplicado', readonly=True, copy=False, ondelete='restrict')
    dolan_converted_from_id = fields.Many2one('sale.order', string='Cotización USD de origen', readonly=True, copy=False, ondelete='restrict')
    dolan_converted_order_ids = fields.One2many('sale.order', 'dolan_converted_from_id', string='Cotizaciones convertidas')
    dolan_converted_order_count = fields.Integer(compute='_compute_dolan_converted_order_count')
    dolan_can_convert_to_ars = fields.Boolean(compute='_compute_dolan_can_convert_to_ars')

    def _compute_dolan_converted_order_count(self):
        for order in self:
            order.dolan_converted_order_count = len(order.dolan_converted_order_ids)

    def _compute_dolan_can_convert_to_ars(self):
        for order in self:
            order.dolan_can_convert_to_ars = (
                order.currency_id.name == 'USD'
                and order.company_id.currency_id.name == 'ARS'
                and order.state in ('draft', 'sent')
            )

    def action_dolan_fetch_bna_rate(self):
        self.ensure_one()
        rate = self.env['dolan.bna.exchange.rate'].fetch_bna_selling_rate(self.company_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cotización BNA Venta'),
            'res_model': 'dolan.bna.exchange.rate',
            'res_id': rate.id,
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'new',
        }

    def action_dolan_convert_to_ars_bna(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Solo se pueden convertir presupuestos sin confirmar.'))
        if self.currency_id.name != 'USD':
            raise UserError(_('Este presupuesto no está expresado en USD.'))
        ars = self.company_id.currency_id
        if ars.name != 'ARS':
            raise UserError(_('La moneda funcional de la empresa no es ARS; no convertí el presupuesto.'))

        rate_record = self.env['dolan.bna.exchange.rate'].fetch_bna_selling_rate(self.company_id)
        target_pricelist = self.env['product.pricelist'].search([
            ('company_id', '=', self.company_id.id), ('currency_id', '=', ars.id),
        ], limit=1) or self.env['product.pricelist'].search([
            ('company_id', '=', False), ('currency_id', '=', ars.id),
        ], limit=1)
        if not target_pricelist:
            raise UserError(_('No hay una lista de precios en ARS para %s.') % self.company_id.display_name)

        line_commands = []
        for line in self.order_line:
            values = {
                'sequence': line.sequence,
                'display_type': line.display_type,
                'name': line.name,
            }
            if not line.display_type:
                uom_field = 'product_uom_id' if 'product_uom_id' in self.env['sale.order.line']._fields else 'product_uom'
                values.update({
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    uom_field: line[uom_field].id,
                    'price_unit': ars.round(line.price_unit * rate_record.rate),
                    'discount': line.discount,
                })
                tax_field = 'tax_ids' if 'tax_ids' in self.env['sale.order.line']._fields else 'tax_id'
                values[tax_field] = [Command.set(line[tax_field].ids)]
            line_commands.append(Command.create(values))

        copy = self.env['sale.order'].with_company(self.company_id).create({
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'company_id': self.company_id.id,
            'pricelist_id': target_pricelist.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'origin': self.name,
            'client_order_ref': self.client_order_ref,
            'validity_date': self.validity_date,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'order_line': line_commands,
            'dolan_converted_from_id': self.id,
            'dolan_exchange_rate': rate_record.rate,
            'dolan_exchange_rate_date': rate_record.rate_date,
            'dolan_exchange_rate_source': rate_record.source_url,
            'dolan_exchange_rate_id': rate_record.id,
        })
        copy.message_post(body=_(
            'Cotización convertida desde %(source)s usando BNA Cotización Billetes, Venta: '
            '1 USD = %(rate)s ARS (fecha %(date)s). El presupuesto USD original se conserva sin cambios.'
        ) % {
            'source': self.display_name,
            'rate': '%.4f' % rate_record.rate,
            'date': fields.Date.to_string(rate_record.rate_date),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Presupuesto convertido a ARS'),
            'res_model': 'sale.order',
            'res_id': copy.id,
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'current',
        }

    def action_dolan_view_converted_quotes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cotizaciones en ARS derivadas'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('dolan_converted_from_id', '=', self.id)],
            'context': {'default_dolan_converted_from_id': self.id},
            'target': 'current',
        }
