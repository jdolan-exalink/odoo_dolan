# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
import json
import logging
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .afipws_connection import AFIP_WS_URLS, ArcaUnavailableError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ar_afip_auth_mode = fields.Selection(
        selection=[
            ('CAE', 'CAE - Código de Autorización Electrónico'),
            ('CAEA', 'CAEA - Código de Autorización Electrónico Anticipado'),
        ],
        string='Modo de Autorización ARCA',
        default='CAE',
        copy=False,
    )
    l10n_ar_afip_auth_code = fields.Char(
        string='CAE / CAEA',
        size=14,
        copy=False,
        tracking=True,
        help='Código de Autorización Electrónico de 14 dígitos otorgado por ARCA/AFIP.',
    )
    l10n_ar_afip_auth_code_due = fields.Date(
        string='Vencimiento CAE',
        copy=False,
        tracking=True,
    )
    l10n_ar_afip_asoc_period_start = fields.Date(
        string='Período asociado desde',
        copy=False,
        help='Período asociado requerido por WSFE para determinadas notas de débito/crédito sin comprobante asociado.',
    )
    l10n_ar_afip_asoc_period_end = fields.Date(
        string='Período asociado hasta',
        copy=False,
        help='Debe ser igual o posterior a la fecha inicial y no posterior a la fecha del comprobante.',
    )
    l10n_ar_caea_id = fields.Many2one(
        'l10n_ar.caea',
        string='CAEA utilizado',
        copy=False,
        readonly=True,
        index='btree_not_null',
        ondelete='restrict',
    )
    l10n_ar_caea_report_state = fields.Selection(
        selection=[
            ('pending', 'Pendiente de informar'),
            ('informed', 'Informado a ARCA'),
            ('rejected', 'Rechazado por ARCA'),
        ],
        string='Informe CAEA',
        copy=False,
        readonly=True,
        tracking=True,
    )
    l10n_ar_caea_generated_at = fields.Datetime(
        string='Generado en contingencia',
        copy=False,
        readonly=True,
        help='Fecha y hora de generación que se informa a ARCA (CbteFchHsGen).',
    )
    l10n_ar_caea_report_message = fields.Char(
        string='Respuesta del informe CAEA',
        copy=False,
        readonly=True,
    )
    l10n_ar_afip_result = fields.Selection(
        selection=[
            ('A', 'Aprobado'),
            ('O', 'Aprobado con Observaciones'),
            ('R', 'Rechazado'),
        ],
        string='Resultado ARCA/AFIP',
        copy=False,
        readonly=True,
        tracking=True,
    )
    l10n_ar_afip_display_status = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('draft_no_cae', 'Borrador (sin CAE)'),
            ('authorized', 'CAE emitido'),
            ('authorized_observations', 'CAE emitido (con observaciones)'),
            ('caea_pending', 'CAEA (pendiente de informar)'),
            ('rejected', 'Rechazado por ARCA'),
            ('cancel', 'Anulado'),
        ],
        string='Estado ARCA',
        compute='_compute_l10n_ar_afip_display_status',
    )
    l10n_ar_afip_cae_indicator = fields.Char(
        string='CAE',
        compute='_compute_l10n_ar_afip_cae_indicator',
    )
    l10n_ar_invoice_date_display = fields.Char(
        string='Fecha',
        compute='_compute_l10n_ar_compact_invoice_dates',
    )
    l10n_ar_invoice_due_date_display = fields.Char(
        string='Vencimiento',
        compute='_compute_l10n_ar_compact_invoice_dates',
    )
    l10n_ar_invoice_vat_amount = fields.Monetary(
        string='IVA',
        currency_field='currency_id',
        compute='_compute_l10n_ar_invoice_vat_amount',
    )
    l10n_ar_company_is_ri = fields.Boolean(
        compute='_compute_l10n_ar_invoice_vat_amount',
    )
    l10n_ar_afip_xml_request = fields.Text(
        string='XML Solicitud ARCA/AFIP',
        copy=False,
        readonly=True,
    )
    l10n_ar_afip_xml_response = fields.Text(
        string='XML Respuesta ARCA/AFIP',
        copy=False,
        readonly=True,
    )
    l10n_ar_afip_qr_code = fields.Char(
        string='URL Código QR ARCA/AFIP (RG 4892)',
        compute='_compute_l10n_ar_afip_qr_and_barcode',
        store=True,
    )
    l10n_ar_afip_barcode = fields.Char(
        string='Código de Barras AFIP (42 dígitos)',
        compute='_compute_l10n_ar_afip_qr_and_barcode',
        store=True,
    )
    l10n_ar_fce_cbu_id = fields.Many2one(
        'res.partner.bank',
        string='CBU para Factura de Crédito Electrónica (MiPyME)',
    )
    l10n_ar_transparent_vat_amount = fields.Monetary(
        string='IVA Contenido (Ley 27.743 Transparencia Fiscal)',
        compute='_compute_l10n_ar_transparent_vat_amount',
        store=True,
        currency_field='currency_id',
        help='Monto de IVA e impuestos nacionales indirectos contenidos en el precio final según Ley 27.743.',
    )

    @api.depends(
        'country_code', 'move_type', 'state', 'l10n_latam_document_type_id',
        'l10n_ar_afip_auth_code', 'l10n_ar_afip_result', 'l10n_ar_caea_report_state',
    )
    def _compute_l10n_ar_afip_display_status(self):
        """Expose fiscal authorization independently of Odoo's accounting state.

        A posted entry without a CAE remains posted for accounting, but must
        look like a draft in the ARCA status indicator until authorization.
        """
        for move in self:
            if (
                move.country_code != 'AR'
                or move.move_type not in ('out_invoice', 'out_refund')
                or not move.l10n_latam_document_type_id
            ):
                move.l10n_ar_afip_display_status = False
            elif move.state == 'cancel':
                move.l10n_ar_afip_display_status = 'cancel'
            elif move.l10n_ar_afip_result == 'R' or move.l10n_ar_caea_report_state == 'rejected':
                move.l10n_ar_afip_display_status = 'rejected'
            elif move.l10n_ar_caea_report_state == 'pending':
                move.l10n_ar_afip_display_status = 'caea_pending'
            elif move.l10n_ar_afip_auth_code:
                move.l10n_ar_afip_display_status = (
                    'authorized_observations'
                    if move.l10n_ar_afip_result == 'O'
                    else 'authorized'
                )
            elif move.state == 'posted':
                move.l10n_ar_afip_display_status = 'draft_no_cae'
            else:
                move.l10n_ar_afip_display_status = 'draft'

    @api.depends('l10n_ar_afip_auth_code')
    def _compute_l10n_ar_afip_cae_indicator(self):
        for move in self:
            move.l10n_ar_afip_cae_indicator = '✓' if move.l10n_ar_afip_auth_code else ''

    @api.depends('invoice_date', 'invoice_date_due')
    def _compute_l10n_ar_compact_invoice_dates(self):
        for move in self:
            move.l10n_ar_invoice_date_display = (
                move.invoice_date.strftime('%d/%m/%Y') if move.invoice_date else ''
            )
            move.l10n_ar_invoice_due_date_display = (
                move.invoice_date_due.strftime('%d/%m/%Y') if move.invoice_date_due else ''
            )

    @api.depends(
        'company_id.l10n_ar_afip_responsibility_type_id.code',
        'currency_id',
        'line_ids.amount_currency',
        'line_ids.tax_line_id',
        'line_ids.tax_line_id.tax_group_id.l10n_ar_vat_afip_code',
        'move_type',
    )
    def _compute_l10n_ar_invoice_vat_amount(self):
        vat_codes = {'3', '4', '5', '6', '8', '9'}
        for move in self:
            is_ri = (move.company_id.l10n_ar_afip_responsibility_type_id.code or '').strip() == '1'
            move.l10n_ar_company_is_ri = is_ri
            if not is_ri:
                move.l10n_ar_invoice_vat_amount = 0.0
                continue

            # Only ARCA VAT tax groups count here; municipal perceptions and
            # other tributes remain outside the IVA column. Customer credit
            # notes display the VAT as a negative amount, like their total.
            vat_amount = sum(
                abs(line.amount_currency)
                for line in move.line_ids.filtered(lambda item: item.tax_line_id)
                if (line.tax_line_id.tax_group_id.l10n_ar_vat_afip_code or '').strip() in vat_codes
            )
            if move.move_type == 'out_refund':
                vat_amount = -vat_amount
            move.l10n_ar_invoice_vat_amount = vat_amount

    def _get_dolan_afip_qr_image(self, box_size=8):
        """QR oficial RG 4892 como data URI PNG para el reporte impreso.

        Se genera en servidor con qrcode[pil] y se embebe como
        ``data:image/png;base64,...``: evita problemas de encoding de la URL
        tanto en wkhtmltopdf como en la vista previa del navegador, y no
        requiere acceso HTTP al controlador /report/barcode.
        """
        self.ensure_one()
        if not self.l10n_ar_afip_qr_code:
            return False
        import io

        import qrcode

        img = qrcode.make(self.l10n_ar_afip_qr_code, box_size=box_size, border=1)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')

    @api.constrains(
        'l10n_ar_afip_asoc_period_start', 'l10n_ar_afip_asoc_period_end',
        'invoice_date', 'l10n_latam_document_type_id',
    )
    def _check_l10n_ar_afip_associated_period(self):
        for move in self:
            date_from = move.l10n_ar_afip_asoc_period_start
            date_to = move.l10n_ar_afip_asoc_period_end
            if bool(date_from) != bool(date_to):
                raise ValidationError(_('Informá ambas fechas del período asociado.'))
            if not date_from:
                continue
            if move.l10n_latam_document_type_id.internal_type not in ('credit_note', 'debit_note'):
                raise ValidationError(_('El período asociado solo corresponde a notas de débito o crédito.'))
            if date_to < date_from:
                raise ValidationError(_('La fecha final del período asociado no puede ser anterior a la inicial.'))
            if move.invoice_date and date_to > move.invoice_date:
                raise ValidationError(_('El período asociado no puede finalizar después de la fecha del comprobante.'))

    @api.depends('amount_tax', 'line_ids.tax_line_id', 'line_ids.price_total', 'line_ids.price_subtotal')
    def _compute_l10n_ar_transparent_vat_amount(self):
        for move in self:
            vat_amount = 0.0
            for line in move.line_ids.filtered(lambda l: l.tax_line_id):
                afip_vat_code = line.tax_line_id.tax_group_id.l10n_ar_vat_afip_code
                if afip_vat_code and afip_vat_code not in ('0', '1', '2'):
                    line_amount = line.amount_currency if line.currency_id == move.currency_id else line.balance
                    vat_amount += abs(line_amount)
            move.l10n_ar_transparent_vat_amount = vat_amount

    @api.depends(
        'move_type',
        'l10n_ar_afip_auth_code',
        'l10n_ar_afip_auth_code_due',
        'invoice_date',
        'amount_total',
        'partner_id.vat',
        'partner_id.l10n_ar_afip_id_value',
        'partner_id.l10n_ar_afip_code',
        'company_id.vat',
        'l10n_latam_document_type_id.code',
        'l10n_latam_document_number',
        'journal_id.l10n_ar_afip_pos_number',
        'currency_id',
        'name',
    )
    def _compute_l10n_ar_afip_qr_and_barcode(self):
        for move in self:
            if (
                move.move_type not in ('out_invoice', 'out_refund')
                or not move.l10n_ar_afip_auth_code
                or move.country_code != 'AR'
            ):
                move.l10n_ar_afip_qr_code = False
                move.l10n_ar_afip_barcode = False
                continue

            company_digits = ''.join(ch for ch in (move.company_id.vat or '') if ch.isdigit())
            partner_code = move.partner_id.l10n_ar_afip_code
            partner_number = move.partner_id.l10n_ar_afip_id_value
            doc_type = move.l10n_latam_document_type_id
            pos_number = move.journal_id.l10n_ar_afip_pos_number
            document_number = move.l10n_latam_document_number or move.name
            auth_code = ''.join(ch for ch in move.l10n_ar_afip_auth_code if ch.isdigit())
            if (
                len(company_digits) != 11 or not partner_code or not partner_number
                or not str(partner_code).isdigit() or not str(partner_number).isdigit()
                or not doc_type or not doc_type.code or not pos_number or not document_number
                or not move.invoice_date or move.currency_id.name != 'ARS'
                or len(auth_code) != 14
            ):
                move.l10n_ar_afip_qr_code = False
                move.l10n_ar_afip_barcode = False
                continue
            try:
                document_parts = move._l10n_ar_get_document_number_parts(document_number, str(doc_type.code))
                cbte_nro = document_parts['invoice_number']
            except (AttributeError, KeyError, TypeError, ValueError):
                move.l10n_ar_afip_qr_code = False
                move.l10n_ar_afip_barcode = False
                continue

            company_cuit = int(company_digits)
            partner_doc_nro = int(partner_number)
            partner_doc_tipo = int(partner_code)
            doc_code = int(doc_type.code)
            if cbte_nro <= 0 or pos_number <= 0:
                move.l10n_ar_afip_qr_code = False
                move.l10n_ar_afip_barcode = False
                continue

            qr_payload = {
                'ver': 1,
                'fecha': move.invoice_date.strftime('%Y-%m-%d'),
                'cuit': company_cuit,
                'ptoVta': int(pos_number),
                'tipoCmp': doc_code,
                'nroCmp': cbte_nro,
                'importe': round(move.amount_total, 2),
                'moneda': 'PES',
                'ctz': 1,
                'tipoDocRec': partner_doc_tipo,
                'nroDocRec': partner_doc_nro,
                'tipoCodAut': 'A' if move.l10n_ar_afip_auth_mode == 'CAEA' else 'E',
                'codAut': int(auth_code),
            }
            json_b64 = base64.b64encode(json.dumps(qr_payload, separators=(',', ':')).encode('utf-8')).decode('ascii')
            move.l10n_ar_afip_qr_code = f"https://www.afip.gob.ar/fe/qr/?p={json_b64}"

            # This module does not have an official ARCA barcode specification or
            # tested encoder. Keep the legacy field empty rather than publishing a guess.
            move.l10n_ar_afip_barcode = False

    def _l10n_ar_build_wsfe_request_xml(self, conn, caea=None):
        """Build a validated single-document WSFEv1 request supported here.

        Without ``caea`` it is a ``FECAESolicitar`` request. With a
        ``l10n_ar.caea`` record it is the ``FECAEARegInformativo`` report of a
        document issued in contingency, carrying the CAEA and its generation
        time (``CbteFchHsGen``).

        A/B invoices and notes are for RI issuers; C invoices and notes are for
        monotributo/exempt issuers. Class C reports the subtotal as ImpNeto and
        never discloses IVA. Other fiscal shapes fail closed.
        """
        self.ensure_one()
        document_type = self.l10n_latam_document_type_id
        if not document_type:
            raise UserError(_('Seleccione un tipo de comprobante argentino antes de construir la solicitud WSFE.'))
        document_code = str(document_type.code or '').strip()
        document_letter = (document_type.l10n_ar_letter or '').strip()
        supported_types = {
            ('out_invoice', 'invoice', 'A'): {'1', '201'},
            ('out_invoice', 'invoice', 'B'): {'6', '206'},
            ('out_invoice', 'invoice', 'C'): {'11', '211'},
            ('out_invoice', 'invoice', 'M'): {'51'},
            ('out_invoice', 'debit_note', 'A'): {'2', '202'},
            ('out_invoice', 'debit_note', 'B'): {'7', '207'},
            ('out_invoice', 'debit_note', 'C'): {'12', '212'},
            ('out_invoice', 'debit_note', 'M'): {'52'},
            ('out_refund', 'credit_note', 'A'): {'3', '203'},
            ('out_refund', 'credit_note', 'B'): {'8', '208'},
            ('out_refund', 'credit_note', 'C'): {'13', '213'},
            ('out_refund', 'credit_note', 'M'): {'53'},
        }
        supported_codes = supported_types.get((self.move_type, document_type.internal_type, document_letter), set())
        if document_code not in supported_codes:
            raise UserError(_('WSFE admite facturas y notas A/B/C/M y MiPyME FCE en ARS; otros comprobantes permanecen bloqueados.'))
        if self.state != 'posted' or not self.invoice_date:
            raise UserError(_('Publique el comprobante y complete su fecha antes de construir la solicitud WSFE.'))
        if not conn or conn.is_simulated or conn.l10n_ar_afip_ws != 'wsfe':
            raise UserError(_('La solicitud requiere una conexión WSFE real, no simulada.'))
        if not conn.token or not conn.sign:
            raise UserError(_('La conexión WSFE no tiene un ticket de acceso vigente.'))

        associated_document = False
        is_note = document_type.internal_type in ('credit_note', 'debit_note')
        period_start = self.l10n_ar_afip_asoc_period_start
        period_end = self.l10n_ar_afip_asoc_period_end
        if is_note:
            if self.move_type == 'out_refund':
                associated_document = self.reversed_entry_id
            elif 'debit_origin_id' in self._fields:
                associated_document = self.debit_origin_id
            if associated_document and (period_start or period_end):
                raise UserError(_('Use un comprobante asociado o un período asociado para la nota, no ambos.'))
            if not associated_document and not (period_start and period_end):
                raise UserError(_('La nota requiere un comprobante asociado o ambas fechas del período asociado.'))
            if period_start and period_end:
                if period_start < fields.Date.from_string('2006-01-02'):
                    raise UserError(_('El período asociado debe comenzar después del 01/01/2006.'))
                if period_end < period_start or period_end > self.invoice_date:
                    raise UserError(_('El período asociado debe ser válido y finalizar como máximo en la fecha de la nota.'))
            if associated_document:
                origin_type = associated_document.l10n_latam_document_type_id
                origin_code = str(origin_type.code or '').strip() if origin_type else ''
                allowed_origin_codes = {'1', '2', '3', '201', '202', '203'} if document_letter == 'A' else ({'6', '7', '8', '206', '207', '208'} if document_letter == 'B' else ({'11', '12', '13', '211', '212', '213'} if document_letter == 'C' else {'51', '52', '53'}))
                origin_cuit = ''.join(char for char in (associated_document.company_id.vat or '') if char.isdigit())
                origin_auth_code = ''.join(char for char in (associated_document.l10n_ar_afip_auth_code or '') if char.isdigit())
                if (
                    associated_document.state != 'posted'
                    or associated_document.company_id != self.company_id
                    or associated_document.partner_id != self.partner_id
                    or associated_document.currency_id != self.currency_id
                    or not origin_type
                    or origin_type.internal_type not in ('invoice', 'credit_note', 'debit_note')
                    or origin_type.l10n_ar_letter != document_letter
                    or origin_code not in allowed_origin_codes
                    or not associated_document.invoice_date
                    or not associated_document.journal_id.l10n_ar_afip_pos_number
                    or len(origin_cuit) != 11
                    or len(origin_auth_code) != 14
                    or associated_document.l10n_ar_afip_result == 'R'
                ):
                    raise UserError(_('El comprobante asociado debe estar publicado, autorizado y coincidir en compañía, cliente, moneda y clase A/B.'))
                try:
                    associated_document._l10n_ar_get_document_number_parts(
                        associated_document.l10n_latam_document_number, origin_code,
                    )
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    raise UserError(_('El comprobante asociado no tiene un número fiscal argentino válido.')) from exc

        company = self.company_id
        issuer_code = (company.l10n_ar_afip_responsibility_type_id.code or '').strip()
        if document_letter in ('A', 'B', 'M') and issuer_code != '1':
            raise UserError(_('Las clases A/B/M requieren una compañía emisora Responsable Inscripta en IVA.'))
        if document_letter == 'C' and issuer_code not in ('4', '6'):
            raise UserError(_('La clase C requiere una compañía emisora Monotributista o Exenta en IVA.'))
        cuit = ''.join(char for char in (company.vat or '') if char.isdigit())
        if company.country_id.code != 'AR' or len(cuit) != 11:
            raise UserError(_('Configure un CUIT argentino de 11 dígitos para la compañía emisora.'))
        if not self.journal_id.l10n_ar_afip_pos_number or self.journal_id.l10n_ar_afip_pos_number <= 0:
            raise UserError(_('Configure el punto de venta ARCA en el diario de ventas.'))
        if not self.l10n_latam_document_number:
            raise UserError(_('El comprobante todavía no tiene un número fiscal asignado.'))

        currency = self.currency_id
        if (
            currency.name != 'ARS'
            or currency.l10n_ar_afip_code != 'PES'
            or company.currency_id != currency
        ):
            raise UserError(_('WSFE solo admite ARS con moneda funcional ARS en esta versión; otras monedas requieren cotización validada.'))
        product_lines = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        if not product_lines or any(not line.product_id for line in product_lines):
            raise UserError(_('WSFE requiere líneas con productos identificados.'))
        if any(line.product_id.type not in ('consu', 'service') for line in product_lines):
            raise UserError(_('WSFE no admite este tipo de producto en el concepto fiscal.'))
        concept = self.l10n_ar_afip_concept
        service_dates = ()
        if concept in ('2', '3'):
            service_start = self.l10n_ar_afip_service_start
            service_end = self.l10n_ar_afip_service_end
            payment_due = self.invoice_date_due
            if not service_start or not service_end or not payment_due:
                raise UserError(_('Para servicios, complete inicio/fin del servicio y fecha de vencimiento.'))
            if service_end < service_start or payment_due < self.invoice_date:
                raise UserError(_('El período del servicio debe ser válido y el vencimiento no puede ser anterior a la factura.'))
            service_dates = (
                ('FchServDesde', service_start.strftime('%Y%m%d')),
                ('FchServHasta', service_end.strftime('%Y%m%d')),
                ('FchVtoPago', payment_due.strftime('%Y%m%d')),
            )
        elif concept != '1':
            raise UserError(_('WSFE solo admite conceptos fiscales de productos, servicios o mixtos.'))

        recipient_condition = self.l10n_ar_afip_responsibility_type_id
        recipient_code = (recipient_condition.code or '').strip()
        if not recipient_code.isdigit():
            raise UserError(_('El destinatario no tiene una condición frente al IVA ARCA válida.'))
        doc_type = (self.partner_id.l10n_ar_afip_code or '').strip()
        doc_number = ''.join(char for char in (self.partner_id.l10n_ar_afip_id_value or '') if char.isdigit())
        if not doc_type.isdigit() or not doc_number:
            raise UserError(_('Complete el tipo y número de documento fiscal del destinatario.'))

        condition_result = conn._call_wsfe_query(
            'FEParamGetCondicionIvaReceptor', {'ClaseCmp': document_type.l10n_ar_letter},
        )
        valid_conditions = {}
        for node in condition_result.iter():
            if node.tag.split('}')[-1] != 'CondicionIvaReceptor':
                continue
            fields_by_name = {
                child.tag.split('}')[-1]: (child.text or '').strip()
                for child in node
            }
            valid_conditions[fields_by_name.get('Id', '')] = fields_by_name.get('Cmp_Clase', '')
        if valid_conditions.get(recipient_code) != document_type.l10n_ar_letter:
            raise UserError(_('La condición IVA del destinatario no pertenece al catálogo ARCA para la clase del comprobante.'))

        # Tax line bases and amounts are in company currency. ARS-only support
        # above makes those values directly usable as WSFE amounts.
        allowed_vat_ids = {'1', '2', '3', '4', '5', '6', '8', '9'}
        iva_by_id = {}
        tribute_by_key = {}
        non_taxable_base = 0.0
        exempt_base = 0.0
        tax_lines = self.line_ids.filtered('tax_line_id')
        round_amount = currency.round
        total_amount = round_amount(abs(self.amount_total))
        for tax_line in tax_lines:
            group = tax_line.tax_line_id.tax_group_id
            vat_id = (group.l10n_ar_vat_afip_code or '').strip()
            tribute_id = (group.l10n_ar_tribute_afip_code or '').strip()
            line_amount = abs(tax_line.amount_currency)
            line_base = abs(tax_line.tax_base_amount)
            if vat_id in allowed_vat_ids:
                if document_letter == 'C':
                    if currency.compare_amounts(line_amount, 0.0):
                        raise UserError(_('Las facturas C no discriminan IVA; quite los impuestos IVA con importe.'))
                    continue
                if vat_id in ('1', '2'):
                    if currency.compare_amounts(line_amount, 0.0):
                        raise UserError(_('Los tratamientos no gravado/exento no pueden generar un importe de impuesto.'))
                    continue
                row = iva_by_id.setdefault(vat_id, {'base': 0.0, 'amount': 0.0})
                row['base'] += line_base
                row['amount'] += line_amount
            elif tribute_id:
                if not tribute_id.isdigit() or tax_line.tax_line_id.amount_type != 'percent':
                    raise UserError(_('WSFE requiere un código ARCA y una alícuota porcentual reconocibles para cada tributo adicional.'))
                tribute_key = (tribute_id, float(tax_line.tax_line_id.amount), group.name or '')
                row = tribute_by_key.setdefault(tribute_key, {'base': 0.0, 'amount': 0.0})
                row['base'] += line_base
                row['amount'] += line_amount
            else:
                raise UserError(_('WSFE no admite tributos o tratamientos fiscales sin mapeo ARCA reconocido.'))

        tax_line_vat_ids = {
            (tax_line.tax_line_id.tax_group_id.l10n_ar_vat_afip_code or '').strip()
            for tax_line in tax_lines
        }
        classified_line_count = 0
        for invoice_line in product_lines:
            vat_codes = set()
            has_tribute = False
            for tax in invoice_line.tax_ids:
                group = tax.tax_group_id
                vat_id = (group.l10n_ar_vat_afip_code or '').strip()
                tribute_id = (group.l10n_ar_tribute_afip_code or '').strip()
                if vat_id:
                    if vat_id not in allowed_vat_ids:
                        raise UserError(_('Cada línea WSFE debe tener un tratamiento de IVA argentino reconocido.'))
                    vat_codes.add(vat_id)
                elif tribute_id.isdigit():
                    if tax.amount_type != 'percent':
                        raise UserError(_('WSFE solo admite tributos adicionales porcentuales mapeados.'))
                    has_tribute = True
                else:
                    raise UserError(_('Cada impuesto de la línea debe tener un código IVA o tributo ARCA reconocido.'))

            if document_letter == 'C':
                if any(code not in ('1', '2', '3') for code in vat_codes):
                    raise UserError(_('El comprobante C no admite IVA discriminado; use solo tratamiento sin IVA.'))
                # Facturas C no informan el IVA discriminado. Una línea sin
                # impuestos es, por tanto, un tratamiento válido sin IVA;
                # algunas líneas migradas o ya contabilizadas no tienen
                # asignado el impuesto 0% aunque su subtotal integre ImpNeto.
                classified_line_count += 1
                continue

            if not vat_codes:
                raise UserError(_('Cada línea WSFE debe tener una clasificación de IVA además de sus tributos adicionales.'))
            if len(vat_codes & {'1', '2'}) > 0:
                if len(vat_codes) != 1:
                    raise UserError(_('No se pueden combinar en una línea los tratamientos no gravado/exento con otra alícuota.'))
                code = next(iter(vat_codes))
                if code == '1':
                    non_taxable_base += abs(invoice_line.price_subtotal)
                else:
                    exempt_base += abs(invoice_line.price_subtotal)
            elif vat_codes == {'3'} and '3' not in tax_line_vat_ids:
                # Odoo can omit zero-amount tax journal items; retain its native
                # 0% tax classification and line subtotal for the WSFE AlicIva.
                row = iva_by_id.setdefault('3', {'base': 0.0, 'amount': 0.0})
                row['base'] += abs(invoice_line.price_subtotal)
            classified_line_count += 1

        if not classified_line_count:
            raise UserError(_('La factura no contiene apuntes fiscales reconocibles para WSFE.'))
        if tribute_by_key:
            tribute_catalog = conn._call_wsfe_query('FEParamGetTiposTributos', {})
            valid_tribute_ids = {
                child.text.strip()
                for node in tribute_catalog.iter()
                if node.tag.split('}')[-1] == 'TributoTipo'
                for child in node
                if child.tag.split('}')[-1] == 'Id' and child.text
            }
            unknown_ids = {key[0] for key in tribute_by_key} - valid_tribute_ids
            if unknown_ids:
                raise UserError(_('El código de tributo %s no figura en el catálogo vigente de ARCA.') % ', '.join(sorted(unknown_ids)))
        for row in tribute_by_key.values():
            row['base'] = round_amount(row['base'])
            row['amount'] = round_amount(row['amount'])
        net_amount = round_amount(sum(row['base'] for row in iva_by_id.values()))
        vat_amount = round_amount(sum(row['amount'] for row in iva_by_id.values()))
        non_taxable_amount = round_amount(non_taxable_base)
        exempt_amount = round_amount(exempt_base)
        tribute_amount = round_amount(sum(row['amount'] for row in tribute_by_key.values()))
        classified_base = round_amount(net_amount + non_taxable_amount + exempt_amount)
        if document_letter == 'C':
            net_amount = round_amount(abs(self.amount_untaxed))
            # C does not disclose VAT. Its whole untaxed subtotal is ImpNeto;
            # additional mapped tributes still travel in Tributos/ImpTrib.
            non_taxable_amount = exempt_amount = vat_amount = 0.0
            if currency.compare_amounts(round_amount(net_amount + tribute_amount), total_amount):
                raise UserError(_('En comprobantes C el total debe coincidir con neto más tributos mapeados.'))
        else:
            if currency.compare_amounts(classified_base, abs(self.amount_untaxed)):
                raise UserError(_('Las bases fiscales reconocidas no coinciden con el neto de la factura.'))
            if currency.compare_amounts(vat_amount, abs(self.amount_tax) - tribute_amount):
                raise UserError(_('El desglose AlicIva no coincide con el IVA de la factura.'))
            if currency.compare_amounts(round_amount(classified_base + vat_amount + tribute_amount), total_amount):
                raise UserError(_('La suma neto + IVA + tributos no coincide con el total de la factura.'))

        try:
            document_parts = self._l10n_ar_get_document_number_parts(
                self.l10n_latam_document_number, document_type.code,
            )
            voucher_number = int(document_parts['invoice_number'])
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise UserError(_('El número fiscal no tiene el formato argentino admitido por WSFE.')) from exc
        if voucher_number <= 0:
            raise UserError(_('El número fiscal debe ser positivo.'))

        def amount_text(value):
            return f'{round_amount(value):.2f}'

        soap_ns = 'http://schemas.xmlsoap.org/soap/envelope/'
        wsfe_ns = 'http://ar.gov.afip.dif.FEV1/'
        ET.register_namespace('soapenv', soap_ns)
        ET.register_namespace('ar', wsfe_ns)
        envelope = ET.Element(f'{{{soap_ns}}}Envelope')
        body = ET.SubElement(envelope, f'{{{soap_ns}}}Body')
        operation_name = 'FECAEARegInformativo' if caea else 'FECAESolicitar'
        operation = ET.SubElement(body, f'{{{wsfe_ns}}}{operation_name}')
        auth = ET.SubElement(operation, f'{{{wsfe_ns}}}Auth')
        ET.SubElement(auth, f'{{{wsfe_ns}}}Token').text = conn.token
        ET.SubElement(auth, f'{{{wsfe_ns}}}Sign').text = conn.sign
        ET.SubElement(auth, f'{{{wsfe_ns}}}Cuit').text = cuit

        cae_request = ET.SubElement(operation, f'{{{wsfe_ns}}}{"FeCAEARegInfReq" if caea else "FeCAEReq"}')
        header = ET.SubElement(cae_request, f'{{{wsfe_ns}}}FeCabReq')
        ET.SubElement(header, f'{{{wsfe_ns}}}CantReg').text = '1'
        ET.SubElement(header, f'{{{wsfe_ns}}}PtoVta').text = str(self.journal_id.l10n_ar_afip_pos_number)
        ET.SubElement(header, f'{{{wsfe_ns}}}CbteTipo').text = document_type.code
        detail_request = ET.SubElement(cae_request, f'{{{wsfe_ns}}}FeDetReq')
        detail = ET.SubElement(detail_request, f'{{{wsfe_ns}}}{"FECAEADetRequest" if caea else "FECAEDetRequest"}')
        values = (
            ('Concepto', concept),
            ('DocTipo', doc_type),
            ('DocNro', doc_number),
            ('CbteDesde', str(voucher_number)),
            ('CbteHasta', str(voucher_number)),
            ('CbteFch', self.invoice_date.strftime('%Y%m%d')),
            ('ImpTotal', amount_text(total_amount)),
            ('ImpTotConc', amount_text(non_taxable_amount)),
            ('ImpNeto', amount_text(net_amount)),
            ('ImpOpEx', amount_text(exempt_amount)),
            ('ImpIVA', amount_text(vat_amount)),
            ('ImpTrib', amount_text(tribute_amount)),
            ('MonId', 'PES'),
            ('MonCotiz', '1.000000'),
            ('CondicionIVAReceptorId', recipient_code),
        ) + service_dates
        for tag, value in values:
            ET.SubElement(detail, f'{{{wsfe_ns}}}{tag}').text = value

        if associated_document:
            origin_type = associated_document.l10n_latam_document_type_id
            origin_parts = associated_document._l10n_ar_get_document_number_parts(
                associated_document.l10n_latam_document_number, str(origin_type.code),
            )
            associated = ET.SubElement(detail, f'{{{wsfe_ns}}}CbtesAsoc')
            item = ET.SubElement(associated, f'{{{wsfe_ns}}}CbteAsoc')
            ET.SubElement(item, f'{{{wsfe_ns}}}Tipo').text = str(origin_type.code)
            ET.SubElement(item, f'{{{wsfe_ns}}}PtoVta').text = str(associated_document.journal_id.l10n_ar_afip_pos_number)
            ET.SubElement(item, f'{{{wsfe_ns}}}Nro').text = str(origin_parts['invoice_number'])
            ET.SubElement(item, f'{{{wsfe_ns}}}Cuit').text = origin_cuit
            ET.SubElement(item, f'{{{wsfe_ns}}}CbteFch').text = associated_document.invoice_date.strftime('%Y%m%d')
        elif is_note:
            period = ET.SubElement(detail, f'{{{wsfe_ns}}}PeriodoAsoc')
            ET.SubElement(period, f'{{{wsfe_ns}}}FchDesde').text = period_start.strftime('%Y%m%d')
            ET.SubElement(period, f'{{{wsfe_ns}}}FchHasta').text = period_end.strftime('%Y%m%d')

        if iva_by_id:
            iva = ET.SubElement(detail, f'{{{wsfe_ns}}}Iva')
            for vat_id in sorted(iva_by_id, key=int):
                row = iva_by_id[vat_id]
                aliquot = ET.SubElement(iva, f'{{{wsfe_ns}}}AlicIva')
                ET.SubElement(aliquot, f'{{{wsfe_ns}}}Id').text = vat_id
                ET.SubElement(aliquot, f'{{{wsfe_ns}}}BaseImp').text = amount_text(row['base'])
                ET.SubElement(aliquot, f'{{{wsfe_ns}}}Importe').text = amount_text(row['amount'])

        if tribute_amount:
            tributes = ET.SubElement(detail, f'{{{wsfe_ns}}}Tributos')
            for (tribute_id, aliquot_rate, description), row in sorted(tribute_by_key.items()):
                if len(description) > 80:
                    raise UserError(_('La descripción del tributo supera los 80 caracteres admitidos por WSFE.'))
                tribute = ET.SubElement(tributes, f'{{{wsfe_ns}}}Tributo')
                ET.SubElement(tribute, f'{{{wsfe_ns}}}Id').text = tribute_id
                ET.SubElement(tribute, f'{{{wsfe_ns}}}Desc').text = description
                ET.SubElement(tribute, f'{{{wsfe_ns}}}BaseImp').text = amount_text(row['base'])
                ET.SubElement(tribute, f'{{{wsfe_ns}}}Alic').text = f'{aliquot_rate:.2f}'
                ET.SubElement(tribute, f'{{{wsfe_ns}}}Importe').text = amount_text(row['amount'])

        if caea:
            if not (caea.code or '').isdigit() or len(caea.code) != 14:
                raise UserError(_('El CAEA asociado no es válido.'))
            if not (caea.date_from <= self.invoice_date <= caea.date_to):
                raise UserError(_('La fecha del comprobante está fuera de la vigencia del CAEA.'))
            generated_at = fields.Datetime.context_timestamp(
                self.with_context(tz='America/Argentina/Buenos_Aires'),
                self.l10n_ar_caea_generated_at or self.create_date or fields.Datetime.now(),
            )
            ET.SubElement(detail, f'{{{wsfe_ns}}}CAEA').text = caea.code
            ET.SubElement(detail, f'{{{wsfe_ns}}}CbteFchHsGen').text = generated_at.strftime('%Y%m%d%H%M%S')

        return ET.tostring(envelope, encoding='utf-8', xml_declaration=True).decode('utf-8')

    def action_l10n_ar_request_cae(self):
        """Request real WSFE authorization. Mocks belong exclusively in tests."""
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund') or move.l10n_ar_afip_auth_code:
                continue
            if move.journal_id.l10n_ar_afip_pos_system == 'DOLAN_CAEA':
                raise UserError(_('Los puntos de venta CAEA no piden CAE: se informan con el CAEA vigente.'))
            wsfe_enabled = self.env['ir.config_parameter'].sudo().get_bool(
                'l10n_ar_afip.wsfe_submission_enabled', default=False,
            )
            if not wsfe_enabled:
                raise UserError(_(
                    'El envío de comprobantes a WSFE está deshabilitado. Solo debe habilitarse '
                    'después de completar y aprobar las pruebas de homologación ARCA.'
                ))
            afip_ws = move.journal_id.l10n_ar_afip_ws or 'wsfe'
            if afip_ws not in ('wsfe', 'wsfex', 'wsmtxca'):
                raise UserError(_('El servicio seleccionado todavía no tiene un emisor implementado y validado.'))
            conn = self.env['l10n_ar.afipws.connection'].get_active_connection(move.company_id, afip_ws)
            if conn.is_simulated:
                raise UserError(_('Un ticket simulado no puede autorizar un comprobante fiscal.'))
            if afip_ws == 'wsfex':
                move._l10n_ar_request_cae_wsfex(conn)
                continue
            if afip_ws == 'wsmtxca':
                move._l10n_ar_request_cae_wsmtxca(conn)
                continue
            req_xml = move._l10n_ar_build_wsfe_request_xml(conn)
            ws_url = AFIP_WS_URLS[conn.type][afip_ws]
            if move.journal_id.l10n_ar_caea_journal_id and not conn._wsfe_check_available(conn.type):
                # Nothing was sent yet: safe to issue the document under CAEA.
                raise ArcaUnavailableError(_('ARCA no responde (FEDummy).'))
            try:
                req = urllib.request.Request(
                    ws_url, data=req_xml.encode('utf-8'),
                    headers={
                        'Content-Type': 'text/xml; charset=utf-8',
                        'SOAPAction': '"http://ar.gov.afip.dif.FEV1/FECAESolicitar"',
                    }, method='POST',
                )
                ssl_context = ssl.create_default_context()
                # Keep certificate/hostname validation and TLS 1.2+, while
                # allowing the same legacy DH group accepted by ARCA's WSFE
                # read-only endpoint from OpenSSL 3 environments.
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                ssl_context.set_ciphers('HIGH:!aNULL:!MD5:@SECLEVEL=1')
                with urllib.request.urlopen(req, timeout=25, context=ssl_context) as response:
                    resp_xml = response.read().decode('utf-8')
                root = ET.fromstring(resp_xml)
                details = [node for node in root.iter() if node.tag.split('}')[-1] == 'FECAEDetResponse']
                if len(details) != 1:
                    errors = self._l10n_ar_wsfe_response_messages(root)
                    suffix = (' ' + '; '.join(errors)) if errors else ''
                    raise UserError(_('ARCA no devolvió una autorización individual válida.%s Consulte el servicio antes de reintentar.') % suffix)
                values = {node.tag.split('}')[-1]: (node.text or '').strip() for node in details[0]}
                cae = values.get('CAE', '')
                due = values.get('CAEFchVto', '')
                if values.get('Resultado') != 'A' or not cae.isdigit() or len(cae) != 14 or len(due) != 8:
                    errors = self._l10n_ar_wsfe_response_messages(root)
                    suffix = (' ' + '; '.join(errors)) if errors else ''
                    raise UserError(_('ARCA no autorizó el comprobante. No se generó ningún CAE local.%s') % suffix)
                due_date = fields.Date.to_date(f'{due[:4]}-{due[4:6]}-{due[6:8]}')
            except UserError:
                raise
            except Exception as exc:
                from .afipws_connection import _is_connection_failure
                # An HTTP answer means ARCA got the request; only connect-phase
                # failures guarantee that no CAE could have been granted.
                if not isinstance(exc, urllib.error.HTTPError) and _is_connection_failure(exc):
                    raise ArcaUnavailableError(_('ARCA no responde (%s).') % type(exc).__name__) from exc
                # Do not expose credential-bearing request/response bodies in errors or logs.
                raise UserError(_(
                    'No se pudo confirmar la autorización ARCA (%s). '
                    'Consulte el comprobante antes de reintentar; no se generó un CAE local.'
                ) % type(exc).__name__) from exc
            # WSFE Auth includes token/sign. Never persist the credential-bearing request.
            request_root = ET.fromstring(req_xml)
            for node in request_root.iter():
                if node.tag.split('}')[-1] in ('Token', 'Sign'):
                    node.text = '[REDACTED]'
            move.write({
                'l10n_ar_afip_auth_code': cae,
                'l10n_ar_afip_auth_code_due': due_date,
                'l10n_ar_afip_result': 'A',
                'l10n_ar_afip_xml_request': ET.tostring(request_root, encoding='unicode'),
                'l10n_ar_afip_xml_response': resp_xml,
            })
        return True

    @api.model
    def _l10n_ar_wsfe_response_messages(self, root):
        """Return safe, compact ARCA rejection details without exposing request credentials."""
        messages = []
        for node in root.iter():
            if node.tag.split('}')[-1] not in ('Err', 'Obs'):
                continue
            values = {child.tag.split('}')[-1]: (child.text or '').strip() for child in node}
            code = values.get('Code', '')
            message = values.get('Msg', '')
            if code or message:
                messages.append(f'{code}: {message}' if code and message else (code or message))
            if len(messages) == 5:
                break
        return [message[:300] for message in messages]

    # ------------------------------------------------------------------
    # Posting with CAE and CAEA contingency
    # ------------------------------------------------------------------
    def _l10n_ar_needs_wsfe_cae(self):
        self.ensure_one()
        return (
            self.country_code == 'AR'
            and self.move_type in ('out_invoice', 'out_refund')
            and self.journal_id.l10n_ar_afip_pos_system in ('DOLAN_WSFE', 'DOLAN_WSFEX', 'DOLAN_WSMTXCA')
            and self.journal_id.l10n_ar_afip_ws
            and not self.l10n_ar_afip_auth_code
        )

    def _post(self, soft=True):
        needs_cae = self.filtered(lambda m: m.state == 'draft' and m._l10n_ar_needs_wsfe_cae())
        with_contingency = needs_cae.filtered(
            lambda m: m.journal_id.l10n_ar_caea_journal_id and m.journal_id.l10n_ar_afip_pos_system == 'DOLAN_WSFE'
        )
        regular = self - with_contingency
        posted = super(AccountMove, regular)._post(soft=soft) if regular else self.browse()
        ar_electronic_moves = (regular & needs_cae).filtered(
            lambda m: m.state == 'posted' and not m.l10n_ar_afip_auth_code
        )
        if ar_electronic_moves:
            ar_electronic_moves.action_l10n_ar_request_cae()
        for move in with_contingency:
            posted |= move._l10n_ar_post_with_caea_contingency(soft)
        return posted

    def _l10n_ar_post_with_caea_contingency(self, soft):
        """Post one document asking for CAE; when ARCA is down, issue it under CAEA.

        The CAE attempt runs inside a savepoint, so a failure rolls back the
        number taken on the CAE point of sale and leaves no gap in its sequence.
        """
        self.ensure_one()
        company = self.company_id
        reason = False
        if not company._l10n_ar_caea_contingency_active():
            try:
                with self.env.cr.savepoint():
                    posted = super(AccountMove, self)._post(soft=soft)
                    if self.state == 'posted' and not self.l10n_ar_afip_auth_code:
                        self.action_l10n_ar_request_cae()
                return posted
            except ArcaUnavailableError as error:
                reason = str(error)
                company.sudo()._l10n_ar_caea_mark_unavailable()
        contingency_journal = self.journal_id.l10n_ar_caea_journal_id
        issue_date = self.invoice_date or fields.Date.context_today(self)
        caea = self.env['l10n_ar.caea'].sudo()._get_valid_for(company, issue_date)
        if not caea:
            raise UserError(_(
                'ARCA no responde y no hay un CAEA vigente para %(date)s. Pedí el CAEA de la quincena '
                'en Contabilidad > Configuración > ARCA / AFIP > CAEA y volvé a intentar.',
                date=issue_date.strftime('%d/%m/%Y'),
            ))
        document_type = self.l10n_latam_document_type_id
        self.write({'journal_id': contingency_journal.id})
        if document_type and self.l10n_latam_document_type_id != document_type:
            self.l10n_latam_document_type_id = document_type
        posted = super(AccountMove, self)._post(soft=soft)
        if self.state != 'posted':
            return posted
        self.write({
            'l10n_ar_afip_auth_mode': 'CAEA',
            'l10n_ar_afip_auth_code': caea.code,
            'l10n_ar_afip_auth_code_due': caea.date_to,
            'l10n_ar_caea_id': caea.id,
            'l10n_ar_caea_report_state': 'pending',
            'l10n_ar_caea_generated_at': fields.Datetime.now(),
        })
        self.message_post(body=_(
            'ARCA no respondió%(reason)s. Comprobante emitido en contingencia con el CAEA %(caea)s; '
            'se informará automáticamente cuando el servicio vuelva.',
            reason=f' ({reason})' if reason else '',
            caea=caea.code,
        ))
        return posted

    def _l10n_ar_caea_inform(self):
        """Report contingency documents with FECAEARegInformativo, one by one."""
        for move in self:
            caea = move.l10n_ar_caea_id
            if not caea or move.l10n_ar_caea_report_state == 'informed' or move.state != 'posted':
                continue
            conn = self.env['l10n_ar.afipws.connection'].get_active_connection(move.company_id, 'wsfe')
            try:
                req_xml = move._l10n_ar_build_wsfe_request_xml(conn, caea=caea)
            except UserError as error:
                move.write({'l10n_ar_caea_report_state': 'rejected', 'l10n_ar_caea_report_message': str(error)[:250]})
                continue
            root = conn._wsfe_post_envelope(req_xml, 'FECAEARegInformativo')
            details = [node for node in root.iter() if node.tag.split('}')[-1] == 'FECAEADetResponse']
            values = {node.tag.split('}')[-1]: (node.text or '').strip() for node in details[0]} if len(details) == 1 else {}
            observations = conn._wsfe_messages(root, tags=('Obs',))
            errors = conn._wsfe_messages(root)
            request_root = ET.fromstring(req_xml)
            for node in request_root.iter():
                if node.tag.split('}')[-1] in ('Token', 'Sign'):
                    node.text = '[REDACTED]'
            audit = {
                'l10n_ar_afip_xml_request': ET.tostring(request_root, encoding='unicode'),
                'l10n_ar_afip_xml_response': ET.tostring(root, encoding='unicode'),
            }
            if values.get('Resultado') == 'A' and values.get('CAEA', caea.code) == caea.code:
                move.write(dict(
                    audit,
                    l10n_ar_caea_report_state='informed',
                    l10n_ar_afip_result='O' if observations else 'A',
                    l10n_ar_caea_report_message='; '.join(observations)[:250] or False,
                ))
            else:
                move.write(dict(
                    audit,
                    l10n_ar_caea_report_state='rejected',
                    l10n_ar_caea_report_message='; '.join(errors + observations)[:250] or _('Rechazado sin detalle.'),
                ))
                move.message_post(body=_('ARCA rechazó el informe CAEA: %s', move.l10n_ar_caea_report_message))
        return True

    def action_l10n_ar_caea_inform(self):
        self.filtered('l10n_ar_caea_id')._l10n_ar_caea_inform()
        return True
