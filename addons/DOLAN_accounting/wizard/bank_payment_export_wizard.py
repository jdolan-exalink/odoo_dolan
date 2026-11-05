# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    exported_to_bank = fields.Boolean(
        string='Exportado a Banco',
        default=False,
        copy=False,
        help='Indica si el pago fue incluido en un lote de transferencias bancarias masivas.',
    )
    bank_export_date = fields.Datetime(
        string='Fecha Exportación Bancaria',
        copy=False,
    )
    bank_export_format = fields.Char(
        string='Formato Bancario Usado',
        copy=False,
    )


class DolanBankPaymentExportWizard(models.TransientModel):
    _name = 'dolan.bank.payment.export.wizard'
    _description = 'Asistente de Exportación de Pagos Masivos a Bancos Argentinos'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Cuenta / Diario Bancario Origen',
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        required=True,
    )
    export_format = fields.Selection(
        selection=[
            ('interbanking', 'Interbanking / Datanet (Universal Argentina)'),
            ('galicia', 'Banco Galicia - Office Banking Pagos'),
            ('santander', 'Banco Santander - Pagos a Proveedores'),
            ('bbva', 'Banco BBVA - Net Cash / Cash Management'),
        ],
        string='Formato de Banca Empresa',
        default='interbanking',
        required=True,
    )
    payment_ids = fields.Many2many(
        'account.payment',
        string='Pagos a Exportar',
        domain="[('payment_type', '=', 'outbound'), ('company_id', '=', company_id), ('state', 'in', ('posted', 'in_process'))]",
    )
    payment_date = fields.Date(
        string='Fecha de Ejecución Pactada',
        default=fields.Date.context_today,
        required=True,
    )
    file_data = fields.Binary(string='Archivo Generado', readonly=True)
    file_name = fields.Char(string='Nombre de Archivo', readonly=True)
    state = fields.Selection(
        selection=[('draft', 'Selección'), ('done', 'Generado')],
        default='draft',
    )
    total_amount = fields.Monetary(
        string='Importe Total del Lote',
        compute='_compute_total_amount',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    payment_count = fields.Integer(
        string='Cantidad de Pagos',
        compute='_compute_total_amount',
    )

    @api.depends('payment_ids')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.payment_ids.mapped('amount'))
            rec.payment_count = len(rec.payment_ids)

    def action_generate_export_file(self):
        self.ensure_one()
        if not self.payment_ids:
            raise UserError(_('Debe seleccionar al menos un pago a proveedor para exportar.'))

        company = self.company_id
        company_vat = ''.join(c for c in (company.vat or '') if c.isdigit()).zfill(11)
        origin_cbu = ''.join(c for c in (self.journal_id.bank_account_id.account_number or '') if c.isdigit())
        if not origin_cbu or len(origin_cbu) != 22:
            raise UserError(_(
                'El diario bancario seleccionado (%s) debe tener configurada una cuenta con un CBU válido de 22 dígitos.'
            ) % self.journal_id.name)

        lines = []
        fmt = self.export_format
        date_str = self.payment_date.strftime('%Y%m%d')

        for idx, payment in enumerate(self.payment_ids, 1):
            dest_partner = payment.partner_id
            dest_vat = ''.join(c for c in (dest_partner.vat or '') if c.isdigit()).zfill(11)
            dest_bank = payment.partner_bank_id or dest_partner.bank_ids[:1]
            dest_cbu = ''.join(c for c in (dest_bank.account_number or '') if c.isdigit())
            if not dest_cbu or len(dest_cbu) != 22:
                raise UserError(_(
                    'El proveedor "%s" del pago %s no tiene un CBU válido de 22 dígitos configurado.'
                ) % (dest_partner.name, payment.name))

            amount_cents = int(round(payment.amount * 100))

            if fmt == 'interbanking':
                # Formato Interbanking / Datanet
                # Registro detalle 01
                rec_line = f"01{dest_vat[:11]}{dest_cbu[:22]}{str(amount_cents).zfill(15)}{date_str}"
                rec_line += (payment.name or '').ljust(15)[:15]
                lines.append(rec_line)

            elif fmt == 'galicia':
                # Formato Banco Galicia Office Banking
                rec_line = f"2{dest_vat[:11]}{dest_cbu[:22]}{str(amount_cents).zfill(15)}"
                rec_line += (dest_partner.name or '').ljust(30)[:30]
                rec_line += (payment.name or '').ljust(15)[:15]
                lines.append(rec_line)

            elif fmt == 'santander':
                # Formato Banco Santander Advance
                rec_line = f"PAG{dest_vat[:11]}{dest_cbu[:22]}{str(amount_cents).zfill(14)}{date_str}"
                rec_line += (payment.name or '').ljust(12)[:12]
                lines.append(rec_line)

            elif fmt == 'bbva':
                # Formato BBVA Net Cash
                rec_line = f"DET{dest_cbu[:22]}{dest_vat[:11]}{str(amount_cents).zfill(15)}{date_str}"
                rec_line += (payment.name or '').ljust(16)[:16]
                lines.append(rec_line)

        # Encabezado y Pie de lote
        total_cents = sum(int(round(p.amount * 100)) for p in self.payment_ids)
        count_str = str(len(self.payment_ids)).zfill(6)
        total_cents_str = str(total_cents).zfill(18)

        if fmt == 'interbanking':
            header = f"00{date_str}{company_vat}{origin_cbu}{'PAGOS PROVEEDORES'.ljust(20)[:20]}"
            trailer = f"99{count_str}{total_cents_str}"
            content_str = "\r\n".join([header] + lines + [trailer]) + "\r\n"
            file_name = f"interbanking_{date_str}.txt"
        elif fmt == 'galicia':
            header = f"1{company_vat}{origin_cbu}{date_str}"
            trailer = f"9{count_str}{total_cents_str}"
            content_str = "\r\n".join([header] + lines + [trailer]) + "\r\n"
            file_name = f"galicia_pagos_{date_str}.txt"
        elif fmt == 'santander':
            header = f"HDR{company_vat}{origin_cbu}{date_str}"
            trailer = f"TRL{count_str}{total_cents_str}"
            content_str = "\r\n".join([header] + lines + [trailer]) + "\r\n"
            file_name = f"santander_{date_str}.txt"
        else: # bbva
            header = f"CAB{company_vat}{origin_cbu}{date_str}"
            trailer = f"FIN{count_str}{total_cents_str}"
            content_str = "\r\n".join([header] + lines + [trailer]) + "\r\n"
            file_name = f"bbva_netcash_{date_str}.txt"

        self.payment_ids.write({
            'exported_to_bank': True,
            'bank_export_date': fields.Datetime.now(),
            'bank_export_format': fmt,
        })

        self.write({
            'file_data': base64.b64encode(content_str.encode('ascii', errors='replace')).decode('ascii'),
            'file_name': file_name,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
