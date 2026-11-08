# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ar_padron_representative_company_id = fields.Many2one(
        'res.company',
        string='Empresa representada en consultas de Padrón',
        domain="[('vat', '!=', False)]",
        help='CUIT titular/representada por el certificado que consulta el Padrón. Puede usarse para consultar desde cualquiera de las compañías de Odoo.',
    )
    l10n_ar_padron_certificate_id = fields.Many2one(
        'certificate.certificate',
        string='Certificado para Padrón ARCA',
        help='Certificado de firma utilizado únicamente para consultas de Padrón ARCA por CUIT.',
    )
    l10n_ar_padron_key_id = fields.Many2one(
        'certificate.key',
        string='Clave privada para Padrón ARCA',
        help='Clave privada asociada al certificado elegido. No se usa para emitir comprobantes.',
    )

    l10n_ar_afip_wsfe_submission_enabled = fields.Boolean(
        string='Habilitar envío de comprobantes WSFE',
        config_parameter='l10n_ar_afip.wsfe_submission_enabled',
        default=False,
        help='Deshabilitado por defecto. Habilitar solo después de aprobar pruebas de homologación ARCA y validar certificados, CUIT, punto de venta e impuestos.',
    )
    l10n_ar_afip_ws_environment = fields.Selection(
        related='company_id.l10n_ar_afip_ws_environment',
        readonly=False,
    )
    l10n_ar_afip_ws_crt_id = fields.Many2one(
        related='company_id.l10n_ar_afip_ws_crt_id',
        readonly=False,
    )
    l10n_ar_afip_ws_key_id = fields.Many2one(
        related='company_id.l10n_ar_afip_ws_key_id',
        readonly=False,
    )
    l10n_ar_afip_verification_type = fields.Selection(
        related='company_id.l10n_ar_afip_verification_type',
        readonly=False,
    )
    l10n_ar_fce_transmission_type = fields.Selection(
        related='company_id.l10n_ar_fce_transmission_type',
        readonly=False,
    )
    l10n_ar_computable_tax_credit = fields.Selection(
        related='company_id.l10n_ar_computable_tax_credit',
        readonly=False,
    )
    l10n_ar_daily_book_start_entry_number = fields.Integer(
        related='company_id.l10n_ar_daily_book_start_entry_number',
        readonly=False,
    )

    @api.model
    def _padron_parameter_ids(self):
        params = self.env['ir.config_parameter'].sudo()
        result = {}
        for field_name, key in (
            ('l10n_ar_padron_representative_company_id', 'dolan_l10n_ar_afip.padron_representative_company_id'),
            ('l10n_ar_padron_certificate_id', 'dolan_l10n_ar_afip.padron_certificate_id'),
            ('l10n_ar_padron_key_id', 'dolan_l10n_ar_afip.padron_key_id'),
        ):
            try:
                result[field_name] = int(params.get_param(key) or 0) or False
            except (TypeError, ValueError):
                result[field_name] = False
        return result

    @api.model
    def _get_dolan_padron_configuration(self):
        """Return the optional shared Padrón signing pair and represented CUIT.

        This configuration applies only to the read-only taxpayer registry
        service; invoice signing continues to use the active company's own
        credentials.
        """
        ids = self._padron_parameter_ids()
        certificate_id = ids['l10n_ar_padron_certificate_id']
        key_id = ids['l10n_ar_padron_key_id']
        representative_company_id = ids['l10n_ar_padron_representative_company_id']
        if not certificate_id and not key_id and not representative_company_id:
            representative = self.env['res.company'].sudo().search([
                ('l10n_ar_afip_ws_crt_id', '!=', False),
                ('l10n_ar_afip_ws_key_id', '!=', False),
                ('vat', '!=', False),
            ], order='id asc', limit=1)
            if representative:
                represented_cuit = ''.join(char for char in representative.vat if char.isdigit())
                return {
                    'certificate': representative.l10n_ar_afip_ws_crt_id.sudo(),
                    'key': representative.l10n_ar_afip_ws_key_id.sudo(),
                    'representative_company': representative,
                    'represented_cuit': represented_cuit,
                }
            return False
        if not certificate_id or not key_id:
            raise UserError(_('Configure tanto el certificado como la clave privada compartidos para el Padrón ARCA.'))

        Certificate = self.env['certificate.certificate'].sudo()
        Key = self.env['certificate.key'].sudo()
        certificate = Certificate.browse(certificate_id).exists()
        key = Key.browse(key_id).exists()
        if not certificate or not key:
            raise UserError(_('El certificado o la clave compartidos para el Padrón ARCA ya no existen.'))
        certificate_key = getattr(certificate, 'private_key_id', False)
        if certificate_key and certificate_key != key:
            raise UserError(_('La clave privada seleccionada no es la asociada al certificado compartido.'))

        representative = self.env['res.company'].sudo().browse(representative_company_id).exists()
        if not representative:
            representative = certificate.company_id
        if not representative or not representative.vat:
            raise UserError(_('Seleccione la empresa titular del certificado y configure su CUIT para las consultas de Padrón.'))
        if certificate.company_id and certificate.company_id != representative:
            raise UserError(_('La empresa representada debe coincidir con la titularidad del certificado seleccionado.'))
        if key.company_id and key.company_id != representative:
            raise UserError(_('La clave privada seleccionada no pertenece a la empresa representada.'))

        represented_cuit = ''.join(char for char in representative.vat if char.isdigit())
        if not self.env['res.partner']._l10n_ar_validate_cuit_checksum(represented_cuit):
            raise UserError(_('La empresa representada debe tener una CUIT válida para consultar el Padrón ARCA.'))
        return {
            'certificate': certificate,
            'key': key,
            'representative_company': representative,
            'represented_cuit': represented_cuit,
        }

    def get_values(self):
        values = super().get_values()
        values.update(self._padron_parameter_ids())
        return values

    def set_values(self):
        previous_ids = self._padron_parameter_ids()
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        mapping = (
            ('l10n_ar_padron_representative_company_id', 'dolan_l10n_ar_afip.padron_representative_company_id'),
            ('l10n_ar_padron_certificate_id', 'dolan_l10n_ar_afip.padron_certificate_id'),
            ('l10n_ar_padron_key_id', 'dolan_l10n_ar_afip.padron_key_id'),
        )
        for field_name, key in mapping:
            params.set_param(key, str(self[field_name].id or '') if self[field_name] else '')
        if any(previous_ids[field] != (self[field].id or False) for field, _key in mapping):
            # Do not keep a still-valid WSAA ticket signed by the previous
            # shared identity after an administrator changes the Padrón pair.
            self.env['l10n_ar.afipws.connection'].sudo().search([
                ('l10n_ar_afip_ws', '=', 'ws_sr_constancia_inscripcion'),
            ]).write({
                'token': False,
                'sign': False,
                'expiration_time': fields.Datetime.now(),
            })

    def action_l10n_ar_test_afip_connection(self):
        return self.company_id.action_l10n_ar_test_afip_connection()

    def action_l10n_ar_generate_csr(self):
        return self.company_id.action_l10n_ar_generate_csr()
