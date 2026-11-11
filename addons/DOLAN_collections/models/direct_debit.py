# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
"""Débito automático por CBU.

El archivo que se genera es un CSV genérico (CUIT; CBU; importe; referencia;
vencimiento; identificador de adhesión). Cada banco tiene su diseño de
débito directo: validar con el banco y ajustar ``_dolan_line_values`` si el
banco exige otro formato.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


class DolanDirectDebitBatch(models.Model):
    _name = 'dolan.direct.debit.batch'
    _description = 'Lote de débito automático'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char('Lote', required=True, default=lambda self: _('Nuevo'), copy=False)
    date = fields.Date('Fecha de débito', required=True, default=fields.Date.context_today)
    due_until = fields.Date('Incluir vencimientos hasta', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Banco', required=True,
                                 domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado al banco'),
        ('done', 'Procesado'),
        ('cancel', 'Anulado'),
    ], default='draft', required=True, tracking=True, copy=False)
    line_ids = fields.One2many('dolan.direct.debit.line', 'batch_id', string='Débitos')
    total = fields.Monetary('Total', compute='_compute_total')
    file_id = fields.Many2one('ir.attachment', string='Archivo para el banco', readonly=True, copy=False)

    @api.depends('line_ids.amount')
    def _compute_total(self):
        for batch in self:
            batch.total = sum(batch.line_ids.mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('dolan.direct.debit.batch') or _('Nuevo')
        return super().create(vals_list)

    def action_load_invoices(self):
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_('Sólo se cargan facturas en lotes en borrador.'))
            already = self.env['dolan.direct.debit.line'].search([
                ('batch_id.state', 'in', ('draft', 'sent')),
            ]).move_id
            invoices = self.env['account.move'].search([
                ('company_id', '=', batch.company_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<=', batch.due_until),
                ('commercial_partner_id.dolan_direct_debit', '=', True),
                ('id', 'not in', already.ids),
            ], order='commercial_partner_id, invoice_date_due')
            batch.write({'line_ids': [fields.Command.create({
                'move_id': move.id,
                'amount': move.amount_residual,
            }) for move in invoices]})
        return True

    def _dolan_line_values(self, line):
        partner = line.partner_id
        return [
            _digits(partner.vat),
            _digits(partner.dolan_direct_debit_bank_id.account_number),
            '%.2f' % line.amount,
            line.move_id.name or '',
            (line.move_id.invoice_date_due or self.date).strftime('%Y%m%d'),
            partner.dolan_direct_debit_ref or '',
        ]

    def action_generate_file(self):
        for batch in self:
            if not batch.line_ids:
                raise UserError(_('El lote no tiene débitos.'))
            invalid = batch.line_ids.filtered(lambda l: len(_digits(l.partner_id.dolan_direct_debit_bank_id.account_number)) != 22)
            if invalid:
                raise UserError(_('Estos clientes no tienen un CBU de 22 dígitos: %s',
                                  ', '.join(invalid.partner_id.mapped('display_name'))))
            rows = ['cuit;cbu;importe;referencia;vencimiento;adhesion']
            rows += [';'.join(batch._dolan_line_values(line)) for line in batch.line_ids]
            attachment = self.env['ir.attachment'].create({
                'name': 'debito_automatico_%s_%s.csv' % (batch.date.strftime('%Y%m%d'), batch.id),
                'raw': ('\r\n'.join(rows) + '\r\n').encode('utf-8'),
                'mimetype': 'text/csv',
                'res_model': batch._name,
                'res_id': batch.id,
            })
            batch.write({'file_id': attachment.id, 'state': 'sent'})
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self[:1].file_id.id,
            'target': 'self',
        }

    def action_register_collections(self):
        """Registra como cobrados los débitos no marcados como rechazados."""
        for batch in self:
            if batch.state != 'sent':
                raise UserError(_('Primero generá el archivo y envialo al banco.'))
            for line in batch.line_ids.filtered(lambda l: l.state == 'pending'):
                wizard = self.env['account.payment.register'].with_context(
                    active_model='account.move', active_ids=line.move_id.ids,
                ).create({
                    'journal_id': batch.journal_id.id,
                    'amount': line.amount,
                    'payment_date': batch.date,
                    'communication': _('Débito automático %s', batch.name),
                })
                payment = wizard._create_payments()
                line.write({'state': 'paid', 'payment_id': payment[:1].id})
            batch.state = 'done'
            rejected = batch.line_ids.filtered(lambda l: l.state == 'rejected')
            if rejected:
                batch.message_post(body=_('Débitos rechazados: %s', ', '.join(rejected.move_id.mapped('name'))))
        return True

    def action_cancel(self):
        if any(batch.state == 'done' for batch in self):
            raise UserError(_('No se puede anular un lote procesado.'))
        self.write({'state': 'cancel'})
        return True


class DolanDirectDebitLine(models.Model):
    _name = 'dolan.direct.debit.line'
    _description = 'Débito automático'

    batch_id = fields.Many2one('dolan.direct.debit.batch', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one('account.move', string='Factura', required=True)
    partner_id = fields.Many2one(related='move_id.commercial_partner_id', store=True, string='Cliente')
    cbu_id = fields.Many2one(related='partner_id.dolan_direct_debit_bank_id', string='CBU')
    currency_id = fields.Many2one(related='batch_id.currency_id')
    amount = fields.Monetary('Importe', required=True)
    state = fields.Selection([
        ('pending', 'A debitar'),
        ('paid', 'Cobrado'),
        ('rejected', 'Rechazado'),
    ], default='pending', required=True)
    reject_reason = fields.Char('Motivo de rechazo')
    payment_id = fields.Many2one('account.payment', string='Cobro', readonly=True)

    def action_mark_rejected(self):
        self.filtered(lambda l: l.state == 'pending').write({'state': 'rejected'})
        return True
