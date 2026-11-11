# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
"""Factura de Crédito Electrónica MiPyME (Ley 27.440) de punta a punta.

- Opcionales obligatorios en WSFE: CBU (2101) y opción de transmisión SCA/ADC
  (27) en la factura; anulación (22) en notas de crédito/débito FCE.
- Consulta de obligación y monto mínimo del receptor (WSFECRED
  ``consultarMontoObligadoRecepcion``) y sugerencia de pasar a FCE.
- Seguimiento de la cuenta corriente de cada FCE emitida
  (``consultarCtaCte``) y aceptación o rechazo de las FCE recibidas
  (``aceptarFECred`` / ``rechazarFECred``).
"""
import logging
import re
import xml.etree.ElementTree as ET

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FECRED_NS = 'http://ar.gob.afip.wsfecred/FECredService/'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
WSFE_NS = 'http://ar.gov.afip.dif.FEV1/'

FCE_INVOICE_CODES = {'201', '206', '211'}
FCE_NOTE_CODES = {'202', '203', '207', '208', '212', '213'}
FCE_CODES = FCE_INVOICE_CODES | FCE_NOTE_CODES
FCE_EQUIVALENT = {'1': '201', '6': '206', '11': '211'}

FCE_STATES = [
    ('pending', 'Pendiente de aceptación'),
    ('accepted', 'Aceptada'),
    ('rejected', 'Rechazada'),
    ('informed', 'Informada a agente de depósito'),
    ('cancelled', 'Cancelada'),
]

REJECTION_REASONS = [
    ('1', 'Falta de entrega de la mercadería o prestación del servicio'),
    ('2', 'Vicios redhibitorios o diferencias en cantidad o calidad'),
    ('3', 'Divergencias en plazos o precios acordados'),
    ('4', 'Vicios en requisitos formales'),
    ('5', 'Defectos de la obligación de pago o del contrato'),
]


def _local(node):
    return node.tag.split('}')[-1]


def _find_text(root, *names):
    for node in root.iter():
        if _local(node) in names and (node.text or '').strip():
            return node.text.strip()
    return ''


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def map_fce_state(text):
    text = (text or '').lower()
    if 'rechaz' in text:
        return 'rejected'
    if 'cancel' in text:
        return 'cancelled'
    if 'informad' in text or 'agente' in text:
        return 'informed'
    if 'acept' in text:
        return 'accepted'
    return 'pending'


class L10nArAfipwsConnection(models.Model):
    _inherit = 'l10n_ar.afipws.connection'

    def _fecred_envelope(self, operation, values):
        self.ensure_one()
        if self.is_simulated or not self.token or not self.sign:
            raise UserError(_('WSFECRED requiere un ticket real de acceso.'))
        cuit = _digits(self.company_id.vat)
        envelope = ET.Element(f'{{{SOAP_NS}}}Envelope')
        body = ET.SubElement(envelope, f'{{{SOAP_NS}}}Body')
        request = ET.SubElement(body, f'{{{FECRED_NS}}}{operation}Request')
        auth = ET.SubElement(request, 'authRequest')
        ET.SubElement(auth, 'token').text = self.token
        ET.SubElement(auth, 'sign').text = self.sign
        ET.SubElement(auth, 'cuitRepresentada').text = cuit

        def fill(parent, data):
            for key, value in data:
                node = ET.SubElement(parent, key)
                if isinstance(value, (list, tuple)):
                    fill(node, value)
                else:
                    node.text = str(value)

        fill(request, values)
        return ET.tostring(envelope, encoding='utf-8', xml_declaration=True)

    def _fecred_call(self, operation, values):
        """Envía la operación y devuelve la raíz de la respuesta, o UserError si ARCA informa errores."""
        self.ensure_one()
        root = self._ws_post_envelope(self._fecred_envelope(operation, values), 'wsfecred', '', operation)
        errors = []
        for container in root.iter():
            if _local(container) != 'arrayErrores':
                continue
            for item in container.iter():
                if _local(item) == 'codigoDescripcion':
                    code = _find_text(item, 'codigo')
                    desc = _find_text(item, 'descripcion')
                    errors.append(('%s: %s' % (code, desc)).strip(': '))
        if errors:
            raise UserError(_('ARCA (WSFECRED %(op)s) informó: %(errors)s', op=operation, errors='; '.join(errors[:5])))
        return root


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_fce_is_mipyme = fields.Boolean(
        'Emisor MiPyME (FCE)',
        help='Marcar si la empresa tiene certificado MiPyME y debe emitir Factura de Crédito Electrónica '
             'a grandes empresas obligadas.')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_fce_obligated = fields.Boolean('Obligado a recibir FCE', copy=False)
    dolan_fce_min_amount = fields.Monetary('Monto mínimo FCE', copy=False,
                                           currency_field='dolan_fce_currency_id')
    dolan_fce_currency_id = fields.Many2one('res.currency', compute='_compute_dolan_fce_currency_id')
    dolan_fce_check_date = fields.Date('Última consulta FCE', copy=False, readonly=True)

    def _compute_dolan_fce_currency_id(self):
        currency = self.env.company.currency_id
        for partner in self:
            partner.dolan_fce_currency_id = currency

    def action_dolan_fce_check(self):
        company = self.env.company
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(company, 'wsfecred')
        today = fields.Date.context_today(self)
        for partner in self:
            cuit = _digits(partner.commercial_partner_id.vat)
            if len(cuit) != 11:
                raise UserError(_('El contacto %s no tiene CUIT válido.', partner.display_name))
            root = conn._fecred_call('consultarMontoObligadoRecepcion', [
                ('cuitConsultada', cuit),
                ('fechaEmision', today.strftime('%Y-%m-%d')),
            ])
            obligated = _find_text(root, 'obligado').upper() in ('S', 'SI', 'TRUE')
            amount = _find_text(root, 'montoDesde') or '0'
            partner.commercial_partner_id.write({
                'dolan_fce_obligated': obligated,
                'dolan_fce_min_amount': float(amount.replace(',', '.')) if obligated else 0.0,
                'dolan_fce_check_date': today,
            })
        return True


class AccountMove(models.Model):
    _inherit = 'account.move'

    dolan_fce_is_fce = fields.Boolean('Es FCE', compute='_compute_dolan_fce_is_fce')
    dolan_fce_suggested = fields.Boolean('Corresponde FCE', compute='_compute_dolan_fce_suggested')
    dolan_fce_cancellation = fields.Boolean(
        'Anulación de FCE', copy=False,
        help='En notas de crédito/débito FCE: informa a ARCA que la nota anula la factura (opcional 22 = S).')
    dolan_fce_state = fields.Selection(FCE_STATES, string='Estado FCE', copy=False, tracking=True)
    dolan_fce_ctacte_code = fields.Char('Código cuenta corriente FCE', copy=False, readonly=True)
    dolan_fce_balance = fields.Monetary('Saldo FCE en ARCA', copy=False, readonly=True)
    dolan_fce_last_check = fields.Datetime('Última consulta FCE', copy=False, readonly=True)
    dolan_fce_rejection_reason = fields.Char('Motivo de rechazo FCE', copy=False, readonly=True)

    @api.depends('l10n_latam_document_type_id.code')
    def _compute_dolan_fce_is_fce(self):
        for move in self:
            move.dolan_fce_is_fce = str(move.l10n_latam_document_type_id.code or '') in FCE_CODES

    @api.depends('move_type', 'state', 'company_id.dolan_fce_is_mipyme',
                 'partner_id.commercial_partner_id.dolan_fce_obligated',
                 'partner_id.commercial_partner_id.dolan_fce_min_amount',
                 'amount_total', 'l10n_latam_document_type_id')
    def _compute_dolan_fce_suggested(self):
        for move in self:
            partner = move.partner_id.commercial_partner_id
            move.dolan_fce_suggested = bool(
                move.move_type == 'out_invoice'
                and move.state == 'draft'
                and move.company_id.dolan_fce_is_mipyme
                and partner.dolan_fce_obligated
                and move.amount_total >= (partner.dolan_fce_min_amount or 0.0)
                and str(move.l10n_latam_document_type_id.code or '') in FCE_EQUIVALENT
            )

    def action_dolan_fce_switch(self):
        for move in self.filtered('dolan_fce_suggested'):
            code = FCE_EQUIVALENT[str(move.l10n_latam_document_type_id.code)]
            doc_type = self.env['l10n_latam.document.type'].search([
                ('country_id.code', '=', 'AR'), ('code', '=', code)], limit=1)
            if not doc_type:
                raise UserError(_('No se encontró el tipo de comprobante FCE %s.', code))
            vals = {'l10n_latam_document_type_id': doc_type.id}
            if not move.l10n_ar_fce_cbu_id:
                vals['l10n_ar_fce_cbu_id'] = move._dolan_fce_default_cbu().id
            move.write(vals)
        return True

    def _dolan_fce_default_cbu(self):
        self.ensure_one()
        banks = self.company_id.partner_id.bank_ids
        return banks.filtered(lambda b: len(_digits(b.account_number)) == 22)[:1]

    # ------------------------------------------------------------------
    # WSFE: opcionales y vencimiento de la FCE
    # ------------------------------------------------------------------
    def _dolan_fce_wsfe_optionals(self):
        self.ensure_one()
        code = str(self.l10n_latam_document_type_id.code or '')
        if code in FCE_INVOICE_CODES:
            cbu = _digits((self.l10n_ar_fce_cbu_id or self._dolan_fce_default_cbu()).account_number)
            if len(cbu) != 22:
                raise UserError(_('La Factura de Crédito Electrónica requiere un CBU de 22 dígitos del emisor.'))
            if not self.invoice_date_due:
                raise UserError(_('La Factura de Crédito Electrónica requiere fecha de vencimiento del pago.'))
            return [('2101', cbu), ('27', self.company_id.l10n_ar_fce_transmission_type or 'SCA')]
        if code in FCE_NOTE_CODES:
            return [('22', 'S' if self.dolan_fce_cancellation else 'N')]
        return []

    def _l10n_ar_build_wsfe_request_xml(self, conn, caea=None):
        request_xml = super()._l10n_ar_build_wsfe_request_xml(conn, caea=caea)
        optionals = self._dolan_fce_wsfe_optionals()
        if not optionals:
            return request_xml
        ET.register_namespace('soapenv', SOAP_NS)
        ET.register_namespace('ar', WSFE_NS)
        root = ET.fromstring(request_xml.encode('utf-8'))
        detail = next(node for node in root.iter() if _local(node) in ('FECAEDetRequest', 'FECAEADetRequest'))
        if str(self.l10n_latam_document_type_id.code) in FCE_INVOICE_CODES \
                and not any(_local(child) == 'FchVtoPago' for child in detail):
            due = ET.Element(f'{{{WSFE_NS}}}FchVtoPago')
            due.text = self.invoice_date_due.strftime('%Y%m%d')
            position = next((i for i, child in enumerate(detail) if _local(child) == 'MonId'), len(detail))
            detail.insert(position, due)
        container = ET.Element(f'{{{WSFE_NS}}}Opcionales')
        for opt_id, value in optionals:
            item = ET.SubElement(container, f'{{{WSFE_NS}}}Opcional')
            ET.SubElement(item, f'{{{WSFE_NS}}}Id').text = opt_id
            ET.SubElement(item, f'{{{WSFE_NS}}}Valor').text = value
        position = next((i for i, child in enumerate(detail) if _local(child) in ('CAEA', 'CbteFchHsGen')), len(detail))
        detail.insert(position, container)
        return ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.filtered(lambda m: m.dolan_fce_is_fce and m.move_type in ('out_invoice', 'in_invoice')
                        and not m.dolan_fce_state).write({'dolan_fce_state': 'pending'})
        return posted

    # ------------------------------------------------------------------
    # WSFECRED: cuenta corriente, aceptación y rechazo
    # ------------------------------------------------------------------
    def _dolan_fce_voucher_id(self):
        self.ensure_one()
        if not self.dolan_fce_is_fce or self.state != 'posted':
            raise UserError(_('El comprobante %s no es una FCE publicada.', self.display_name))
        parts = re.findall(r'\d+', self.l10n_latam_document_number or '')
        if len(parts) < 2:
            raise UserError(_('El comprobante %s no tiene número fiscal.', self.display_name))
        issuer = self.company_id.vat if self.move_type.startswith('out_') else self.partner_id.commercial_partner_id.vat
        return [
            ('CUITEmisor', _digits(issuer)),
            ('codTipoCmp', str(self.l10n_latam_document_type_id.code)),
            ('ptoVta', str(int(parts[-2]))),
            ('nroCmp', str(int(parts[-1]))),
        ]

    def _dolan_fce_connection(self):
        self.ensure_one()
        return self.env['l10n_ar.afipws.connection'].get_active_connection(self.company_id, 'wsfecred')

    def action_dolan_fce_refresh(self):
        for move in self:
            root = move._dolan_fce_connection()._fecred_call('consultarCtaCte', [
                ('idComprobante', move._dolan_fce_voucher_id()),
            ])
            balance = _find_text(root, 'saldo') or '0'
            move.write({
                'dolan_fce_state': map_fce_state(_find_text(root, 'estado', 'descEstado', 'estadoCtaCte')),
                'dolan_fce_ctacte_code': _find_text(root, 'codCtaCte') or move.dolan_fce_ctacte_code,
                'dolan_fce_balance': float(balance.replace(',', '.')),
                'dolan_fce_last_check': fields.Datetime.now(),
            })
        return True

    def action_dolan_fce_accept(self):
        for move in self:
            if move.move_type != 'in_invoice':
                raise UserError(_('Sólo se aceptan FCE recibidas de proveedores.'))
            move._dolan_fce_connection()._fecred_call('aceptarFECred', [
                ('idComprobante', move._dolan_fce_voucher_id()),
                ('saldoAceptado', '%.2f' % move.amount_total),
                ('codMoneda', 'PES'),
                ('cotizacionMonedaUlt', '1'),
            ])
            move.write({'dolan_fce_state': 'accepted', 'dolan_fce_last_check': fields.Datetime.now()})
            move.message_post(body=_('FCE aceptada en ARCA.'))
        return True

    def _dolan_fce_reject(self, reason_code, justification):
        for move in self:
            if move.move_type != 'in_invoice':
                raise UserError(_('Sólo se rechazan FCE recibidas de proveedores.'))
            label = dict(REJECTION_REASONS)[reason_code]
            move._dolan_fce_connection()._fecred_call('rechazarFECred', [
                ('idComprobante', move._dolan_fce_voucher_id()),
                ('arrayMotivosRechazo', [('motivoRechazo', [
                    ('codMotivo', reason_code),
                    ('descMotivo', label),
                    ('justificacion', justification or label),
                ])]),
            ])
            move.write({
                'dolan_fce_state': 'rejected',
                'dolan_fce_rejection_reason': '%s - %s' % (label, justification or ''),
                'dolan_fce_last_check': fields.Datetime.now(),
            })
            move.message_post(body=_('FCE rechazada en ARCA: %s', label))
        return True

    def action_dolan_fce_reject_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar FCE'),
            'res_model': 'dolan.fce.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_ids': self.ids},
        }

    @api.model
    def _cron_dolan_fce_refresh(self, limit=50):
        moves = self.search([
            ('dolan_fce_state', '=', 'pending'),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'in_invoice')),
        ], order='dolan_fce_last_check asc nulls first', limit=limit)
        for move in moves:
            try:
                with self.env.cr.savepoint():
                    move.action_dolan_fce_refresh()
            except UserError as exc:
                _logger.info('FCE %s: no se pudo consultar ARCA: %s', move.display_name, exc)


class DolanFceRejectWizard(models.TransientModel):
    _name = 'dolan.fce.reject.wizard'
    _description = 'Rechazo de Factura de Crédito Electrónica'

    move_ids = fields.Many2many('account.move', string='Comprobantes')
    reason = fields.Selection(REJECTION_REASONS, string='Motivo', required=True, default='2')
    justification = fields.Text('Justificación')

    def action_confirm(self):
        self.move_ids._dolan_fce_reject(self.reason, self.justification)
        return {'type': 'ir.actions.act_window_close'}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dolan_fce_is_mipyme = fields.Boolean(related='company_id.dolan_fce_is_mipyme', readonly=False)
