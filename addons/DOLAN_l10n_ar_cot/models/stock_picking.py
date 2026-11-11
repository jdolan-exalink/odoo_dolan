# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PBA = 'B'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dolan_cot_required = fields.Boolean('Requiere COT', compute='_compute_dolan_cot_required')
    dolan_cot_state = fields.Selection([
        ('none', 'Sin COT'),
        ('done', 'COT obtenido'),
        ('error', 'Rechazado'),
    ], string='Estado COT', default='none', copy=False, tracking=True)
    dolan_cot_number = fields.Char('Número de COT', copy=False, tracking=True)
    dolan_cot_date = fields.Datetime('Fecha de solicitud COT', copy=False, readonly=True)
    dolan_cot_message = fields.Text('Respuesta de ARBA', copy=False, readonly=True)
    dolan_cot_file_id = fields.Many2one('ir.attachment', string='Archivo COT', copy=False, readonly=True)
    dolan_cot_carrier_id = fields.Many2one('res.partner', string='Transportista')
    dolan_cot_vehicle_plate = fields.Char('Patente del vehículo')
    dolan_cot_trailer_plate = fields.Char('Patente del acoplado')
    dolan_cot_departure = fields.Datetime('Salida del transporte')
    dolan_cot_route_type = fields.Selection([('U', 'Urbano'), ('R', 'Rural')], string='Tipo de recorrido',
                                            default='U')
    dolan_cot_amount = fields.Monetary('Valor de la mercadería', compute='_compute_dolan_cot_amount',
                                       currency_field='dolan_cot_currency_id')
    dolan_cot_currency_id = fields.Many2one(related='company_id.currency_id')

    @api.depends('move_ids.quantity', 'move_ids.product_uom_qty', 'move_ids.product_id')
    def _compute_dolan_cot_amount(self):
        for picking in self:
            total = 0.0
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                qty = move.quantity or move.product_uom_qty
                sale_line = move.sale_line_id if 'sale_line_id' in move._fields else False
                if sale_line:
                    price = sale_line.price_unit * (1 - (sale_line.discount or 0.0) / 100.0)
                    price = sale_line.product_uom_id._compute_price(price, move.uom_id) \
                        if 'product_uom_id' in sale_line._fields else price
                else:
                    price = move.product_id.uom_id._compute_price(move.product_id.lst_price, move.uom_id)
                total += qty * price
            picking.dolan_cot_amount = total

    @api.depends('company_id.dolan_cot_enabled', 'company_id.dolan_cot_min_amount', 'picking_type_id.code',
                 'partner_id.state_id', 'picking_type_id.warehouse_id.partner_id.state_id', 'dolan_cot_amount')
    def _compute_dolan_cot_required(self):
        for picking in self:
            company = picking.company_id
            origin = picking.picking_type_id.warehouse_id.partner_id or company.partner_id
            states = {picking.partner_id.state_id.code, origin.state_id.code}
            picking.dolan_cot_required = bool(
                company.dolan_cot_enabled
                and picking.picking_type_id.code == 'outgoing'
                and PBA in states
                and picking.partner_id.country_id.code in (False, 'AR')
                and picking.dolan_cot_amount >= (company.dolan_cot_min_amount or 0.0)
            )

    def _dolan_cot_unique_code(self):
        """Tipo de comprobante (3) + letra + punto de venta (4) + número (8)."""
        self.ensure_one()
        number = self.l10n_ar_delivery_guide_number or ''
        parts = re.findall(r'\d+', number)
        if len(parts) < 2:
            raise UserError(_('El remito %s no tiene número de remito R.', self.name))
        doc_type = self.env['l10n_latam.document.type']
        if self.l10n_ar_cai_data:
            doc_type = doc_type.browse(self.l10n_ar_cai_data.get('document_type_id'))
        doc_type = doc_type or self.picking_type_id.l10n_ar_document_type_id
        code = int(re.sub(r'\D', '', doc_type.code or '91') or 91)
        letter = doc_type.l10n_ar_letter or 'R'
        return '%03d%s%04d%08d' % (code, letter, int(parts[-2]), int(parts[-1]))

    def _dolan_cot_check_ready(self):
        self.ensure_one()
        errors = []
        if self.state != 'done':
            errors.append(_('el remito no está validado'))
        if not self.l10n_ar_delivery_guide_number:
            errors.append(_('falta generar el remito R'))
        if not self.partner_id.street or not self.partner_id.city or not self.partner_id.state_id:
            errors.append(_('el destinatario no tiene calle, localidad y provincia'))
        if self.dolan_cot_state == 'done':
            errors.append(_('ya tiene COT %s', self.dolan_cot_number))
        if errors:
            raise UserError(_('No se puede pedir COT para %(name)s: %(errors)s.',
                              name=self.name, errors=', '.join(errors)))

    def action_dolan_request_cot(self):
        pickings = self.filtered(lambda p: p.dolan_cot_state != 'done')
        if not pickings:
            raise UserError(_('Los remitos seleccionados ya tienen COT.'))
        for company in pickings.company_id:
            self.env['dolan.cot.service'].request_cot(pickings.filtered(lambda p: p.company_id == company))
        failed = pickings.filtered(lambda p: p.dolan_cot_state == 'error')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('COT ARBA'),
                'message': _('%(ok)s remito(s) con COT, %(ko)s rechazado(s).',
                             ok=len(pickings) - len(failed), ko=len(failed)),
                'type': 'warning' if failed else 'success',
                'sticky': bool(failed),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_dolan_reset_cot(self):
        self.write({'dolan_cot_state': 'none', 'dolan_cot_number': False, 'dolan_cot_message': False})
        return True

    def l10n_ar_action_create_delivery_guide(self):
        res = super().l10n_ar_action_create_delivery_guide()
        to_request = self.filtered(lambda p: p.company_id.dolan_cot_auto and p.dolan_cot_required
                                   and p.dolan_cot_state != 'done')
        for picking in to_request:
            try:
                with self.env.cr.savepoint():
                    self.env['dolan.cot.service'].request_cot(picking)
            except UserError as exc:
                picking.write({'dolan_cot_state': 'error', 'dolan_cot_message': str(exc)})
                _logger.info('COT automático no obtenido para %s: %s', picking.name, exc)
        return res
