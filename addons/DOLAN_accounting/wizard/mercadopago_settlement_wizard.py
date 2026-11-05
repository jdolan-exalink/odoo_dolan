# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import csv
import io
import logging
from decimal import Decimal, InvalidOperation

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DolanMercadoPagoSettlementWizard(models.TransientModel):
    _name = 'dolan.mercadopago.settlement.wizard'
    _description = 'Conciliador de Liquidaciones y Liberaciones Mercado Pago'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Contable',
        required=True,
        domain="[('type', 'in', ('bank', 'general'))]",
        default=lambda self: self.env['account.journal'].search([('type', 'in', ('bank', 'general'))], limit=1),
        help='Diario donde se asentará la liquidación y la apertura de comisiones / retenciones.',
    )
    date = fields.Date(
        string='Fecha Contable',
        required=True,
        default=fields.Date.context_today,
    )
    attachment_file = fields.Binary(
        string='Reporte de Liquidación (CSV)',
        required=True,
        help='Archivo CSV oficial de Mercado Pago ("Reporte de Liberaciones" o "Todas las transacciones").',
    )
    attachment_filename = fields.Char(string='Nombre del Archivo')

    # Cuentas contables para la distribución
    account_mp_clearing_id = fields.Many2one(
        'account.account',
        string='Cuenta Cobros MP (Puente / Crédito)',
        required=True,
        help='Cuenta transitoria donde se imputaron los cobros brutos de clientes (ej. 1.1.2 Mercado Pago o Deudores por Ventas).',
    )
    account_net_dest_id = fields.Many2one(
        'account.account',
        string='Cuenta Destino Fondos (Banco / Débito)',
        required=True,
        help='Cuenta de Banco o Dinero Disponible donde ingresa el importe neto real.',
    )
    account_fee_id = fields.Many2one(
        'account.account',
        string='Cuenta Comisión Mercado Pago (Gasto)',
        required=True,
        help='Cuenta de resultado negativo para la tarifa por servicio / comisión de Mercado Pago.',
    )
    account_financing_id = fields.Many2one(
        'account.account',
        string='Cuenta Costo Financiero (Cuotas)',
        required=True,
        help='Cuenta de gastos por financiamiento o promociones de cuotas sin interés.',
    )
    account_taxes_id = fields.Many2one(
        'account.account',
        string='Cuenta Retenciones e IVA Sufrido (Activo)',
        required=True,
        help='Cuenta de crédito fiscal para Retenciones de IVA, Ganancias e Ingresos Brutos (SIRCUPA/ARBA/AGIP).',
    )

    # Totales procesados
    total_gross = fields.Monetary(string='Total Bruto Cobrado', readonly=True)
    total_fee = fields.Monetary(string='Total Comisiones MP', readonly=True)
    total_financing = fields.Monetary(string='Total Costo Financiero', readonly=True)
    total_taxes = fields.Monetary(string='Total Retenciones / Impuestos', readonly=True)
    total_net = fields.Monetary(string='Total Neto Acreditado', readonly=True)
    transaction_count = fields.Integer(string='Cantidad de Operaciones', readonly=True)

    move_id = fields.Many2one('account.move', string='Asiento Contable Generado', readonly=True)
    state = fields.Selection([
        ('draft', 'Selección de Archivo'),
        ('done', 'Liquidación Contabilizada'),
    ], default='draft', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        # Auto-completar cuentas habituales si existen
        accounts = self.env['account.account'].search([('company_ids', 'in', company.id)])
        for acc in accounts:
            code = acc.code or ''
            name = (acc.name or '').lower()
            if not res.get('account_net_dest_id') and ('banco' in name or code.startswith('1.1.1')):
                res['account_net_dest_id'] = acc.id
            if not res.get('account_mp_clearing_id') and ('mercado pago' in name or 'clearing' in name or 'cobro' in name):
                res['account_mp_clearing_id'] = acc.id
            if not res.get('account_fee_id') and ('comisi' in name or 'gasto bancario' in name):
                res['account_fee_id'] = acc.id
            if not res.get('account_financing_id') and ('financiero' in name or 'interes' in name):
                res['account_financing_id'] = acc.id
            if not res.get('account_taxes_id') and ('retenci' in name or 'percepci' in name or 'iva' in name):
                res['account_taxes_id'] = acc.id
        # Fallback a cuentas disponibles para no bloquear
        any_acc = accounts[:1].id if accounts else False
        for fld in ('account_mp_clearing_id', 'account_net_dest_id', 'account_fee_id', 'account_financing_id', 'account_taxes_id'):
            if not res.get(fld) and any_acc:
                res[fld] = any_acc
        return res

    def _parse_amount(self, val_str):
        if not val_str:
            return Decimal('0.00')
        s = str(val_str).replace('$', '').replace('ARS', '').strip().replace(' ', '')
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return Decimal('0.00')

    def action_process_settlement(self):
        self.ensure_one()
        raw_bytes = self.attachment_file.content if hasattr(self.attachment_file, 'content') else self.attachment_file
        if not raw_bytes:
            raise UserError(_("Por favor seleccione un archivo CSV de liquidación de Mercado Pago."))

        text = raw_bytes.decode('utf-8-sig', errors='replace')
        if not text.strip():
            text = raw_bytes.decode('latin1', errors='replace')

        delimiter = ';' if text.count(';') > text.count(',') else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [list(r) for r in reader if r and any(str(c or '').strip() for c in r)]

        if not raw_rows:
            raise UserError(_("El archivo seleccionado está vacío."))

        # 1. Identificar encabezado
        header_idx = None
        for i, row in enumerate(raw_rows[:15]):
            row_lower = [str(c or '').strip().lower() for c in row]
            if any(k in c for c in row_lower for k in ('gross', 'net', 'fee', 'bruto', 'neto', 'tarifa', 'operation_id', 'source_id')):
                header_idx = i
                break

        if header_idx is None:
            raise UserError(_("No se detectaron columnas de liquidación de Mercado Pago (ej. GROSS_AMOUNT, MP_FEE, NET_CREDIT_AMOUNT)."))

        header = [str(c or '').strip().lower() for c in raw_rows[header_idx]]
        data_rows = raw_rows[header_idx + 1:]

        # Identificar índices de columnas
        def find_col(keywords):
            for i, h in enumerate(header):
                if any(k in h for k in keywords):
                    return i
            return None

        idx_gross = find_col(['gross_amount', 'monto_bruto', 'transaction_amount', 'total_amount', 'bruto'])
        idx_fee = find_col(['mp_fee_amount', 'mercadopago_fee', 'fee', 'comision', 'tarifa'])
        idx_financing = find_col(['financing_fee_amount', 'costo_financiamiento', 'financing', 'cuotas'])
        idx_taxes = find_col(['taxes_amount', 'taxes', 'retenciones', 'impuestos', 'iva_comision'])
        idx_net = find_col(['net_credit_amount', 'net_received_amount', 'neto', 'net_amount'])

        tot_gross = Decimal('0.00')
        tot_fee = Decimal('0.00')
        tot_financing = Decimal('0.00')
        tot_taxes = Decimal('0.00')
        tot_net = Decimal('0.00')
        count = 0

        for r in data_rows:
            if not any(str(c or '').strip() for c in r):
                continue
            gross = abs(self._parse_amount(r[idx_gross])) if idx_gross is not None and idx_gross < len(r) else Decimal('0.00')
            fee = abs(self._parse_amount(r[idx_fee])) if idx_fee is not None and idx_fee < len(r) else Decimal('0.00')
            financing = abs(self._parse_amount(r[idx_financing])) if idx_financing is not None and idx_financing < len(r) else Decimal('0.00')
            taxes = abs(self._parse_amount(r[idx_taxes])) if idx_taxes is not None and idx_taxes < len(r) else Decimal('0.00')

            if idx_net is not None and idx_net < len(r):
                net = self._parse_amount(r[idx_net])
                net = abs(net) if net != Decimal('0.00') else (gross - fee - financing - taxes)
            else:
                net = gross - fee - financing - taxes

            tot_gross += gross
            tot_fee += fee
            tot_financing += financing
            tot_taxes += taxes
            tot_net += net
            count += 1

        if count == 0 or tot_gross == Decimal('0.00'):
            raise UserError(_("No se encontraron importes válidos para liquidar en el archivo."))

        # Asegurar balance estricto: Neto = Bruto - Gastos
        calculated_net = tot_gross - (tot_fee + tot_financing + tot_taxes)
        if abs(tot_net - calculated_net) > Decimal('0.05'):
            tot_net = calculated_net

        # Crear Asiento Contable
        move_lines = []
        # 1. Débito a Banco / Dinero Disponible (Neto)
        if tot_net > Decimal('0.00'):
            move_lines.append((0, 0, {
                'name': f"Liquidación MP - Neto Acreditado ({count} ops)",
                'account_id': self.account_net_dest_id.id,
                'debit': float(tot_net),
                'credit': 0.0,
            }))
        # 2. Débito a Gastos Comisiones MP
        if tot_fee > Decimal('0.00'):
            move_lines.append((0, 0, {
                'name': "Liquidación MP - Tarifa / Comisiones de procesamiento",
                'account_id': self.account_fee_id.id,
                'debit': float(tot_fee),
                'credit': 0.0,
            }))
        # 3. Débito a Gastos Financieros (Cuotas)
        if tot_financing > Decimal('0.00'):
            move_lines.append((0, 0, {
                'name': "Liquidación MP - Costo Financiero de cuotas",
                'account_id': self.account_financing_id.id,
                'debit': float(tot_financing),
                'credit': 0.0,
            }))
        # 4. Débito a Retenciones e Impuestos (Activo Fiscal)
        if tot_taxes > Decimal('0.00'):
            move_lines.append((0, 0, {
                'name': "Liquidación MP - Retenciones Sufridas (IVA / Ganancias / IIBB)",
                'account_id': self.account_taxes_id.id,
                'debit': float(tot_taxes),
                'credit': 0.0,
            }))
        # 5. Crédito a Cuenta Puente Mercado Pago (Bruto cobrado)
        if tot_gross > Decimal('0.00'):
            move_lines.append((0, 0, {
                'name': f"Liquidación MP - Cancelación Ventas Brutas Cobradas ({count} ops)",
                'account_id': self.account_mp_clearing_id.id,
                'debit': 0.0,
                'credit': float(tot_gross),
            }))

        move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': f"Liquidación Mercado Pago {self.attachment_filename or self.date}",
            'move_type': 'entry',
            'line_ids': move_lines,
        })

        self.write({
            'total_gross': float(tot_gross),
            'total_fee': float(tot_fee),
            'total_financing': float(tot_financing),
            'total_taxes': float(tot_taxes),
            'total_net': float(tot_net),
            'transaction_count': count,
            'move_id': move.id,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asiento de Liquidación Mercado Pago'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }
