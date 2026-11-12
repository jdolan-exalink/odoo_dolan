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

    l10n_ar_arca_cert_state = fields.Selection(
        [
            ('none', 'Sin certificado'),
            ('valid', 'Vigente'),
            ('expiring', 'Vence pronto'),
            ('expired', 'Vencido'),
        ],
        string='Estado del certificado ARCA',
        compute='_compute_l10n_ar_arca_status',
    )
    l10n_ar_arca_cert_summary = fields.Char(compute='_compute_l10n_ar_arca_status')
    l10n_ar_arca_waiting_request_id = fields.Many2one(
        'l10n_ar.arca.certificate.request',
        string='Pedido pendiente',
        compute='_compute_l10n_ar_arca_status',
    )
    l10n_ar_arca_padron_summary = fields.Char(compute='_compute_l10n_ar_arca_status')

    @api.depends('company_id')
    def _compute_l10n_ar_arca_status(self):
        Request = self.env['l10n_ar.arca.certificate.request'].sudo()
        now = fields.Datetime.now()
        for settings in self:
            company = settings.company_id.sudo()
            cert = company.l10n_ar_afip_ws_crt_id
            env_label = dict(company._fields['l10n_ar_afip_ws_environment'].selection).get(
                company.l10n_ar_afip_ws_environment, '')
            if not cert or not company.l10n_ar_afip_ws_key_id:
                settings.l10n_ar_arca_cert_state = 'none'
                settings.l10n_ar_arca_cert_summary = _('%s todavía no tiene certificado ARCA cargado.') % company.name
            else:
                date_end = cert.date_end
                if date_end and date_end < now:
                    state = 'expired'
                elif date_end and (date_end - now).days < 30:
                    state = 'expiring'
                else:
                    state = 'valid'
                settings.l10n_ar_arca_cert_state = state
                settings.l10n_ar_arca_cert_summary = _(
                    '%(name)s · %(env)s · vence el %(date)s',
                    name=cert.name or cert.subject_common_name or '',
                    env=env_label,
                    date=date_end.strftime('%d/%m/%Y') if date_end else '-',
                )
            settings.l10n_ar_arca_waiting_request_id = Request.search([
                ('company_id', '=', company.id), ('state', '=', 'waiting'),
            ], limit=1)
            try:
                shared = settings._get_dolan_padron_configuration()
            except UserError as error:
                settings.l10n_ar_arca_padron_summary = str(error)
            else:
                settings.l10n_ar_arca_padron_summary = (
                    _('Las consultas de CUIT usan el certificado de %s.') % shared['representative_company'].name
                    if shared else _('No hay ninguna empresa con certificado para consultar el padrón.')
                )

    def action_l10n_ar_arca_new_request(self):
        return self._l10n_ar_arca_open_new_request(self.company_id or self.env.company)

    @api.model
    def _l10n_ar_arca_open_new_request(self, company):
        Request = self.env['l10n_ar.arca.certificate.request']
        request = Request.search([('company_id', '=', company.id), ('state', '=', 'draft')], limit=1)
        if not request:
            request = Request.create({
                'company_id': company.id,
                'environment': company.l10n_ar_afip_ws_environment or 'production',
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pedido de certificado ARCA'),
            'res_model': 'l10n_ar.arca.certificate.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_l10n_ar_arca_upload_certificate(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cargar certificado de ARCA'),
            'res_model': 'l10n_ar.arca.certificate.upload',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
                'default_request_id': self.l10n_ar_arca_waiting_request_id.id,
            },
        }

    def action_l10n_ar_arca_requests(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pedidos de certificado ARCA'),
            'res_model': 'l10n_ar.arca.certificate.request',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_l10n_ar_test_padron_connection(self):
        return self.company_id.action_l10n_ar_test_padron_connection()

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
                result[field_name] = int(params.get_str(key) or 0) or False
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
            params.set_str(key, str(self[field_name].id or '') if self[field_name] else '')
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
        return self._l10n_ar_arca_open_new_request(self.company_id)
