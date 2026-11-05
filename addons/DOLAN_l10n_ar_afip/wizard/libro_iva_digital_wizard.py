# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
import io
import re
import zipfile
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class L10nArLibroIvaDigitalWizard(models.TransientModel):
    _name = 'l10n_ar.libro.iva.digital.wizard'
    _description = 'Exportador limitado de Libro IVA Digital (ARCA)'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.context_today,
    )
    export_type = fields.Selection(
        selection=[
            ('libro_iva', 'Libro IVA Digital (4 archivos TXT + ZIP)'),
            ('sicore', 'SICORE / SIRE (Retenciones y Percepciones ARCA)'),
        ],
        string='Tipo de Presentación',
        required=True,
        default='libro_iva',
    )
    prorate_tax_credit = fields.Boolean(
        string='Prorrateo de Crédito Fiscal Global',
        default=False,
    )

    # Archivos generados
    ventas_cbte_file = fields.Binary(string='LIBRO_IVA_DIGITAL_VENTAS_CBTE.txt', readonly=True)
    ventas_cbte_filename = fields.Char(default='LIBRO_IVA_DIGITAL_VENTAS_CBTE.txt')
    ventas_alicuotas_file = fields.Binary(string='LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS.txt', readonly=True)
    ventas_alicuotas_filename = fields.Char(default='LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS.txt')
    compras_cbte_file = fields.Binary(string='LIBRO_IVA_DIGITAL_COMPRAS_CBTE.txt', readonly=True)
    compras_cbte_filename = fields.Char(default='LIBRO_IVA_DIGITAL_COMPRAS_CBTE.txt')
    compras_alicuotas_file = fields.Binary(string='LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS.txt', readonly=True)
    compras_alicuotas_filename = fields.Char(default='LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS.txt')
    sicore_file = fields.Binary(string='SICORE_RETENCIONES.txt', readonly=True)
    sicore_filename = fields.Char(default='SICORE_RETENCIONES.txt')
    zip_file = fields.Binary(string='Paquete Completo ZIP', readonly=True)
    zip_filename = fields.Char(default='ARCA_LIBRO_IVA_DIGITAL.zip')
    summary_text = fields.Text(string='Resumen de Liquidación', readonly=True)

    def _fmt_amount(self, amount, length=15):
        """Formatea un importe en centavos sin punto decimal, relleno con ceros a la izquierda."""
        cents = int(round(abs(amount or 0.0) * 100))
        if len(str(cents)) > length:
            raise UserError(_("El importe excede el ancho permitido por el archivo fiscal."))
        return f"{cents:0{length}d}"

    @staticmethod
    def _extract_pos_and_number(move):
        document_number = move.l10n_latam_document_number or move.name
        if not document_number or '-' not in document_number:
            raise UserError(_("El comprobante %(move)s no tiene punto de venta y número fiscal verificables.", move=move.display_name))
        try:
            parts = move._l10n_ar_get_document_number_parts(
                document_number, str(move.l10n_latam_document_type_id.code or ''),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise UserError(_("No se pudo interpretar el número fiscal de %(move)s.", move=move.display_name)) from exc
        pos, num = parts.get('point_of_sale'), parts.get('invoice_number')
        if not pos or not num:
            raise UserError(_("El comprobante %(move)s no tiene punto de venta y número fiscal válidos.", move=move.display_name))
        return int(pos), int(num)

    def _get_book_identity(self, move):
        if not move.invoice_date or not move.l10n_latam_document_type_id or not move.l10n_latam_document_type_id.code:
            raise UserError(_("El comprobante %(move)s no tiene fecha o tipo fiscal.", move=move.display_name))
        if move.currency_id.name != 'ARS':
            raise UserError(_("El Libro IVA Digital aún requiere validación de moneda/cotización para %(move)s.", move=move.display_name))
        doc_type = move.partner_id.l10n_ar_afip_code or (80 if (move.partner_id.vat and len(re.sub(r'\D', '', move.partner_id.vat)) == 11) else 99)
        raw_doc_num = move.partner_id.l10n_ar_afip_id_value or move.partner_id.vat or '0'
        doc_number = re.sub(r'\D', '', str(raw_doc_num)) or '0'
        pos, number = self._extract_pos_and_number(move)
        return {
            'date': move.invoice_date.strftime('%Y%m%d'),
            'document_type': int(move.l10n_latam_document_type_id.code),
            'pos': pos,
            'number': number,
            'partner_type': int(doc_type),
            'partner_number': int(doc_number),
        }

    def _get_vat_details(self, move):
        if not hasattr(move, '_get_vat') or not hasattr(move, '_l10n_ar_get_amounts'):
            raise UserError(_("Se requiere la localización argentina nativa de Odoo para calcular el Libro IVA."))
        base_lines = move._get_rounded_base_and_tax_lines()[0] if hasattr(move, '_get_rounded_base_and_tax_lines') else None
        amounts = move._l10n_ar_get_amounts(base_lines=base_lines) if base_lines else move._l10n_ar_get_amounts()
        details = move._get_vat(base_lines=base_lines) if base_lines else move._get_vat()
        vat_total = sum(item['Importe'] for item in details)
        if not move.currency_id.is_zero(vat_total - amounts['vat_amount']):
            raise UserError(_("El detalle de alícuotas de %(move)s no concilia con el IVA calculado.", move=move.display_name))
        # Until every ARCA tribute/perception is mapped and cross-checked, export only
        # invoices whose tax total consists exclusively of IVA. Never duplicate an
        # unclassified tax into an arbitrary Libro IVA field.
        if not move.currency_id.is_zero(abs(move.amount_tax) - abs(amounts['vat_amount'])):
            raise UserError(_("%(move)s contiene percepciones u otros tributos aún no soportados por este exportador.", move=move.display_name))
        taxable_bases = (
            amounts['vat_taxable_amount']
            + amounts['vat_untaxed_base_amount']
            + amounts['vat_exempt_base_amount']
        )
        if not move.currency_id.is_zero(abs(taxable_bases) - abs(move.amount_untaxed)):
            raise UserError(_("Las bases fiscales de %(move)s no concilian con el neto contable.", move=move.display_name))
        return amounts, details

    def _build_ventas_files(self, moves):
        """Genera LIBRO_IVA_DIGITAL_VENTAS_CBTE (266 chars) y LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS (62 chars)."""
        cbte_lines = []
        alic_lines = []
        for move in moves:
            identity = self._get_book_identity(move)
            amounts, vat_details = self._get_vat_details(move)
            fch = identity['date']
            doc_code, pos, num = identity['document_type'], identity['pos'], identity['number']
            doc_tipo = identity['partner_type']
            doc_nro = f"{identity['partner_number']:020d}"
            partner_name = (move.partner_id.name or 'CONSUMIDOR FINAL')[:30].ljust(30)

            imp_total = self._fmt_amount(move.amount_total, 15)
            imp_no_grav = self._fmt_amount(amounts['vat_untaxed_base_amount'], 15)
            imp_percep_nc = self._fmt_amount(amounts['vat_perc_amount'], 15)
            imp_exento = self._fmt_amount(amounts['vat_exempt_base_amount'], 15)
            imp_percep_nac = self._fmt_amount(amounts['profits_perc_amount'], 15)
            imp_percep_iibb = self._fmt_amount(amounts['iibb_perc_amount'], 15)
            imp_percep_mun = self._fmt_amount(amounts['mun_perc_amount'], 15)
            imp_internos = self._fmt_amount(amounts['intern_tax_amount'], 15)
            moneda = 'PES'
            cotiz = '0001000000'
            if len(vat_details) > 9:
                raise UserError(_("El comprobante %(move)s supera el máximo de alícuotas del formato.", move=move.display_name))
            cant_alic = str(len(vat_details))
            cod_op = '0'
            otros_trib = self._fmt_amount(0.0, 15)
            fch_vto = (move.invoice_date_due or move.invoice_date).strftime('%Y%m%d')

            # Registro de 266 posiciones exactas RG 4597
            cbte_line = (
                f"{fch}"                 # 1-8 (8)
                f"{doc_code:03d}"        # 9-11 (3)
                f"{pos:05d}"             # 12-16 (5)
                f"{num:020d}"            # 17-36 (20)
                f"{num:020d}"            # 37-56 (20)
                f"{doc_tipo:02d}"        # 57-58 (2)
                f"{doc_nro}"             # 59-78 (20)
                f"{partner_name}"        # 79-108 (30)
                f"{imp_total}"           # 109-123 (15)
                f"{imp_no_grav}"         # 124-138 (15)
                f"{imp_percep_nc}"       # 139-153 (15)
                f"{imp_exento}"          # 154-168 (15)
                f"{imp_percep_nac}"      # 169-183 (15)
                f"{imp_percep_iibb}"     # 184-198 (15)
                f"{imp_percep_mun}"      # 199-213 (15)
                f"{imp_internos}"        # 214-228 (15)
                f"{moneda}"              # 229-231 (3)
                f"{cotiz}"               # 232-241 (10)
                f"{cant_alic}"           # 242-242 (1)
                f"{cod_op}"              # 243-243 (1)
                f"{otros_trib}"          # 244-258 (15)
                f"{fch_vto}"             # 259-266 (8)
            )
            cbte_lines.append(cbte_line)

            # Registro Alícuota Ventas (62 posiciones exactas)
            for vat in vat_details:
                alic_line = (
                    f"{doc_code:03d}"
                    f"{pos:05d}"
                    f"{num:020d}"
                    f"{self._fmt_amount(vat['BaseImp'], 15)}"
                    f"{int(vat['Id']):04d}"
                    f"{self._fmt_amount(vat['Importe'], 15)}"
                )
                alic_lines.append(alic_line)

        return '\r\n'.join(cbte_lines) + ('\r\n' if cbte_lines else ''), '\r\n'.join(alic_lines) + ('\r\n' if alic_lines else '')

    def _build_compras_files(self, moves):
        """Genera LIBRO_IVA_DIGITAL_COMPRAS_CBTE (325 chars) y LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS (84 chars)."""
        cbte_lines = []
        alic_lines = []
        for move in moves:
            identity = self._get_book_identity(move)
            amounts, vat_details = self._get_vat_details(move)
            fch = identity['date']
            doc_code, pos, num = identity['document_type'], identity['pos'], identity['number']
            despacho = ''.ljust(16)
            doc_tipo = identity['partner_type']
            doc_nro = f"{identity['partner_number']:020d}"
            partner_name = (move.partner_id.name or 'PROVEEDOR')[:30].ljust(30)

            imp_total = self._fmt_amount(move.amount_total, 15)
            imp_no_grav = self._fmt_amount(amounts['vat_untaxed_base_amount'], 15)
            imp_exento = self._fmt_amount(amounts['vat_exempt_base_amount'], 15)
            imp_percep_iva = self._fmt_amount(amounts['vat_perc_amount'], 15)
            imp_percep_nac = self._fmt_amount(amounts['profits_perc_amount'], 15)
            imp_percep_iibb = self._fmt_amount(amounts['iibb_perc_amount'], 15)
            imp_percep_mun = self._fmt_amount(amounts['mun_perc_amount'], 15)
            imp_internos = self._fmt_amount(amounts['intern_tax_amount'], 15)
            moneda = 'PES'
            cotiz = '0001000000'
            if move.l10n_latam_document_type_id.l10n_ar_letter in ('B', 'C') and amounts['vat_amount']:
                raise UserError(_("El comprobante %(move)s requiere una regla validada para comprobantes B/C con IVA discriminado.", move=move.display_name))
            if len(vat_details) > 9:
                raise UserError(_("El comprobante %(move)s supera el máximo de alícuotas del formato.", move=move.display_name))
            cant_alic = '0' if move.l10n_latam_document_type_id.l10n_ar_letter in ('B', 'C') else str(len(vat_details))
            cod_op = '0'
            cred_fiscal = self._fmt_amount(amounts['vat_amount'] if not self.prorate_tax_credit else 0.0, 15)
            otros_trib = self._fmt_amount(0.0, 15)
            cuit_corredor = '0' * 11
            denom_corredor = ' ' * 30
            iva_comision = self._fmt_amount(0.0, 15)

            cbte_line = (
                f"{fch}"                 # 1-8 (8)
                f"{doc_code:03d}"        # 9-11 (3)
                f"{pos:05d}"             # 12-16 (5)
                f"{num:020d}"            # 17-36 (20)
                f"{despacho}"            # 37-52 (16)
                f"{doc_tipo:02d}"        # 53-54 (2)
                f"{doc_nro}"             # 55-74 (20)
                f"{partner_name}"        # 75-104 (30)
                f"{imp_total}"           # 105-119 (15)
                f"{imp_no_grav}"         # 120-134 (15)
                f"{imp_exento}"          # 135-149 (15)
                f"{imp_percep_iva}"      # 150-164 (15)
                f"{imp_percep_nac}"      # 165-179 (15)
                f"{imp_percep_iibb}"     # 180-194 (15)
                f"{imp_percep_mun}"      # 195-209 (15)
                f"{imp_internos}"        # 210-224 (15)
                f"{moneda}"              # 225-227 (3)
                f"{cotiz}"               # 228-237 (10)
                f"{cant_alic}"           # 238-238 (1)
                f"{cod_op}"              # 239-239 (1)
                f"{cred_fiscal}"         # 240-254 (15)
                f"{otros_trib}"          # 255-269 (15)
                f"{cuit_corredor}"       # 270-280 (11)
                f"{denom_corredor}"      # 281-310 (30)
                f"{iva_comision}"        # 311-325 (15)
            )
            cbte_lines.append(cbte_line)

            if move.l10n_latam_document_type_id.l10n_ar_letter not in ('B', 'C'):
                for vat in vat_details:
                    alic_line = (
                        f"{doc_code:03d}"
                        f"{pos:05d}"
                        f"{num:020d}"
                        f"{doc_tipo:02d}"
                        f"{doc_nro}"
                        f"{self._fmt_amount(vat['BaseImp'], 15)}"
                        f"{int(vat['Id']):04d}"
                        f"{self._fmt_amount(vat['Importe'], 15)}"
                    )
                    alic_lines.append(alic_line)

        return '\r\n'.join(cbte_lines) + ('\r\n' if cbte_lines else ''), '\r\n'.join(alic_lines) + ('\r\n' if alic_lines else '')

    def _build_sicore_file(self):
        certs = self.env['dolan.retention.certificate'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'confirmed'),
        ], order='date asc, id asc')
        lines = []
        for cert in certs:
            lines.append(cert.generate_sicore_line().strip('\r\n'))
        return '\r\n'.join(lines) + ('\r\n' if lines else '')

    def action_generate_files(self):
        """Genera los archivos de Libro IVA Digital o SICORE con datos fiscales de la localización nativa."""
        self.ensure_one()
        period_str = self.date_from.strftime('%Y%m')

        if self.export_type == 'sicore':
            sicore_txt = self._build_sicore_file()
            certs = self.env['dolan.retention.certificate'].search([
                ('company_id', '=', self.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('state', '=', 'confirmed'),
            ])
            self.write({
                'sicore_file': base64.b64encode(sicore_txt.encode('latin-1', errors='replace')).decode('ascii'),
                'sicore_filename': f"ARCA_SICORE_{period_str}.txt",
                'summary_text': _(
                    "Período: %(from)s al %(to)s\n"
                    "Certificados de Retención procesados para SICORE: %(cnt)d\n"
                    "Monto Total Retenido: $ %(total).2f",
                    **{
                        'from': self.date_from,
                        'to': self.date_to,
                        'cnt': len(certs),
                        'total': sum(certs.mapped('amount')),
                    }
                ),
            })
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

        if self.prorate_tax_credit:
            raise UserError(_("El prorrateo de crédito fiscal no está implementado; no se genera un archivo con importes supuestos."))
        base_domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ]
        ventas_moves = self.env['account.move'].search(
            base_domain + [('move_type', 'in', ('out_invoice', 'out_refund'))],
            order='invoice_date asc, id asc',
        )
        compras_moves = self.env['account.move'].search(
            base_domain + [('move_type', 'in', ('in_invoice', 'in_refund'))],
            order='invoice_date asc, id asc',
        )

        v_cbte, v_alic = self._build_ventas_files(ventas_moves)
        c_cbte, c_alic = self._build_compras_files(compras_moves)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('LIBRO_IVA_DIGITAL_VENTAS_CBTE.txt', v_cbte.encode('latin-1', errors='replace'))
            zf.writestr('LIBRO_IVA_DIGITAL_VENTAS_ALICUOTAS.txt', v_alic.encode('latin-1', errors='replace'))
            zf.writestr('LIBRO_IVA_DIGITAL_COMPRAS_CBTE.txt', c_cbte.encode('latin-1', errors='replace'))
            zf.writestr('LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS.txt', c_alic.encode('latin-1', errors='replace'))

        period_str = self.date_from.strftime('%Y%m')
        self.write({
            'ventas_cbte_file': base64.b64encode(v_cbte.encode('latin-1', errors='replace')).decode('ascii'),
            'ventas_alicuotas_file': base64.b64encode(v_alic.encode('latin-1', errors='replace')).decode('ascii'),
            'compras_cbte_file': base64.b64encode(c_cbte.encode('latin-1', errors='replace')).decode('ascii'),
            'compras_alicuotas_file': base64.b64encode(c_alic.encode('latin-1', errors='replace')).decode('ascii'),
            'zip_file': base64.b64encode(zip_buffer.getvalue()).decode('ascii'),
            'zip_filename': f"ARCA_LIBRO_IVA_{period_str}.zip",
            'summary_text': _(
                "Período: %(from)s al %(to)s\n"
                "Comprobantes de Venta procesados: %(v_cnt)d (Débito Fiscal IVA: $ %(v_tax).2f)\n"
                "Comprobantes de Compra procesados: %(c_cnt)d (Crédito Fiscal IVA: $ %(c_tax).2f)\n"
                "Saldo Técnico IVA del Período: $ %(bal).2f",
                **{
                    'from': self.date_from,
                    'to': self.date_to,
                    'v_cnt': len(ventas_moves),
                    'v_tax': sum(ventas_moves.mapped('amount_tax')),
                    'c_cnt': len(compras_moves),
                    'c_tax': sum(compras_moves.mapped('amount_tax')),
                    'bal': sum(ventas_moves.mapped('amount_tax')) - sum(compras_moves.mapped('amount_tax')),
                }
            ),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
