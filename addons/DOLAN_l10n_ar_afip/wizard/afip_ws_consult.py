# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import xml.etree.ElementTree as ET
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class L10nArAfipWsConsult(models.TransientModel):
    _name = 'l10n_ar_afip.ws.consult'
    _description = 'Consulta de Comprobantes en Webservice ARCA/AFIP (FECompUltimoAutorizado / FECompConsultar)'

    journal_id = fields.Many2one(
        'account.journal',
        string='Diario / Punto de Venta',
        required=True,
        domain="[('type', '=', 'sale')]",
        default=lambda self: self.env['account.journal'].search([('type', '=', 'sale')], limit=1),
    )
    available_document_type_ids = fields.Many2many(
        'l10n_latam.document.type',
        compute='_compute_available_document_type_ids',
        string='Tipos de Comprobante Disponibles',
    )
    document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de Comprobante',
        required=True,
        domain="[('id', 'in', available_document_type_ids)]",
    )
    consult_type = fields.Selection(
        selection=[
            ('last', 'Último Comprobante Autorizado (FECompUltimoAutorizado)'),
            ('specific', 'Comprobante Específico (FECompConsultar)'),
        ],
        string='Tipo de Consulta',
        required=True,
        default='last',
    )
    number = fields.Integer(
        string='Número de Comprobante',
        default=1,
    )
    result_text = fields.Text(
        string='Respuesta de ARCA/AFIP',
        readonly=True,
    )
    recovered_move_id = fields.Many2one(
        'account.move', string='Comprobante local actualizado', readonly=True,
    )
    recovery_status = fields.Char(string='Resultado de recuperación', readonly=True)

    @api.depends('journal_id')
    def _compute_available_document_type_ids(self):
        doc_types = self.env['l10n_latam.document.type'].search([('country_id.code', '=', 'AR')])
        if not doc_types:
            doc_types = self.env['l10n_latam.document.type'].search([])
        for rec in self:
            rec.available_document_type_ids = doc_types
            if not rec.document_type_id and doc_types:
                rec.document_type_id = doc_types[0]

    def action_consult_afip(self):
        """Ejecuta la consulta FECompUltimoAutorizado o FECompConsultar y formatea el resultado."""
        self.ensure_one()
        company = self.journal_id.company_id or self.env.company
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(
            company, self.journal_id.l10n_ar_afip_ws or 'wsfe'
        )
        pos_number = getattr(self.journal_id, 'l10n_ar_afip_pos_number', 1) or 1
        doc_code = int(self.document_type_id.code or 1)

        if pos_number <= 0 or doc_code <= 0 or (self.consult_type == 'specific' and self.number <= 0):
            raise UserError(_('Indique punto de venta, tipo y número de comprobante válidos.'))
        method = 'FECompUltimoAutorizado' if self.consult_type == 'last' else 'FECompConsultar'
        values = {'PtoVta': pos_number, 'CbteTipo': doc_code} if self.consult_type == 'last' else {
            'CbteTipo': doc_code, 'CbteNro': self.number, 'PtoVta': pos_number,
        }
        result = conn._call_wsfe_query(method, values)

        def decode(node):
            if not len(node):
                return node.text or ''
            output = {}
            for child in node:
                key = child.tag.split('}')[-1]
                value = decode(child)
                if key in output:
                    output[key] = output[key] + [value] if isinstance(output[key], list) else [output[key], value]
                else:
                    output[key] = value
            return output

        payload = {'Metodo': method, 'Ambiente': conn.type, 'Fuente': 'ARCA WSFE', 'Respuesta': decode(result)}
        self.result_text = json.dumps(payload, indent=2, ensure_ascii=False)
        self.recovered_move_id = False
        self.recovery_status = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import_authorization(self):
        """Copy ARCA's CAE to one exact, already-posted local voucher.

        This intentionally does not create or post accounting moves. Missing or
        mismatching local invoices must be reconciled manually before recovery.
        """
        self.ensure_one()
        if self.consult_type != 'specific':
            raise UserError(_('Seleccione un comprobante específico para recuperar su autorización.'))
        company = self.journal_id.company_id or self.env.company
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(
            company, self.journal_id.l10n_ar_afip_ws or 'wsfe'
        )
        pos_number = self.journal_id.l10n_ar_afip_pos_number
        doc_code = int(self.document_type_id.code or 0)
        if not pos_number or pos_number <= 0 or doc_code <= 0 or self.number <= 0:
            raise UserError(_('Indique punto de venta, tipo y número válidos.'))
        result = conn._call_wsfe_query('FECompConsultar', {
            'CbteTipo': doc_code, 'CbteNro': self.number, 'PtoVta': pos_number,
        })
        response = {}
        for node in result.iter():
            if node.tag.split('}')[-1] == 'ResultGet':
                response = {
                    child.tag.split('}')[-1]: (child.text or '').strip()
                    for child in node
                    if len(child) == 0
                }
                break
        cae = response.get('CodAutorizacion') or response.get('CAE') or ''
        due = response.get('FchVto') or response.get('CAEFchVto') or ''
        if response.get('Resultado') != 'A' or not cae.isdigit() or len(cae) != 14 or len(due) != 8:
            raise UserError(_('ARCA no devolvió un comprobante aprobado con CAE y vencimiento válidos.'))
        for field_name, expected, label in (
            ('CbteTipo', doc_code, _('El tipo de comprobante informado por ARCA no coincide con la consulta.')),
            ('PtoVta', pos_number, _('El punto de venta informado por ARCA no coincide con el diario.')),
            ('CbteDesde', self.number, _('El número informado por ARCA no coincide con el comprobante consultado.')),
            ('CbteHasta', self.number, _('El rango informado por ARCA no corresponde a un comprobante individual.')),
        ):
            if response.get(field_name):
                try:
                    returned_number = int(response[field_name])
                except (TypeError, ValueError) as exc:
                    raise UserError(_('ARCA devolvió un valor no numérico para %s.') % field_name) from exc
                if returned_number != expected:
                    raise UserError(label)

        document_number = f'{pos_number:05d}-{self.number:08d}'
        candidates = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('journal_id', '=', self.journal_id.id),
            ('l10n_latam_document_type_id', '=', self.document_type_id.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
        ])
        local_moves = candidates.filtered(lambda move: move.l10n_latam_document_number == document_number)
        if len(local_moves) != 1:
            raise UserError(_(
                'No existe exactamente un comprobante publicado con el mismo tipo, diario, punto de venta y número. '
                'La recuperación no crea facturas automáticamente.'
            ))
        move = local_moves
        if move.invoice_date.strftime('%Y%m%d') != response.get('CbteFch'):
            raise UserError(_('La fecha del comprobante local no coincide con ARCA. No se importó el CAE.'))
        partner_number = ''.join(char for char in (
            move.partner_id.l10n_ar_afip_id_value or move.partner_id.vat or ''
        ) if char.isdigit())
        if response.get('DocNro') and partner_number != ''.join(char for char in response['DocNro'] if char.isdigit()):
            raise UserError(_('El documento del cliente local no coincide con ARCA. No se importó el CAE.'))
        if not response.get('ImpTotal'):
            raise UserError(_('ARCA no informó el importe total para cotejar el comprobante.'))
        try:
            arca_total = float(response['ImpTotal'])
        except (TypeError, ValueError) as exc:
            raise UserError(_('ARCA devolvió un importe inválido.')) from exc
        if move.currency_id.name != 'ARS' or move.currency_id.compare_amounts(abs(move.amount_total), abs(arca_total)):
            raise UserError(_('El total o la moneda local no coinciden con ARCA. No se importó el CAE.'))
        if move.l10n_ar_afip_auth_code and move.l10n_ar_afip_auth_code != cae:
            raise UserError(_('El comprobante local ya tiene otro CAE. Se bloqueó la sobrescritura.'))
        try:
            due_date = fields.Date.to_date(f'{due[:4]}-{due[4:6]}-{due[6:8]}')
        except (TypeError, ValueError) as exc:
            raise UserError(_('ARCA devolvió una fecha de vencimiento inválida.')) from exc
        response_xml = ET.tostring(result, encoding='unicode')
        move.write({
            'l10n_ar_afip_auth_code': cae,
            'l10n_ar_afip_auth_code_due': due_date,
            'l10n_ar_afip_result': 'A',
            'l10n_ar_afip_xml_response': response_xml,
        })
        self.recovered_move_id = move
        self.recovery_status = _('CAE importado tras cotejar los datos locales con ARCA.')
        self.result_text = json.dumps({
            'Metodo': 'FECompConsultar',
            'Ambiente': conn.type,
            'Fuente': 'ARCA WSFE',
            'ComprobanteLocal': move.display_name,
            'CAE': cae,
            'CAEFchVto': due,
            'Estado': self.recovery_status,
        }, indent=2, ensure_ascii=False)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
