# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ar_afip_ws_environment = fields.Selection(
        selection=[
            ('testing', 'Homologación (Testing)'),
            ('production', 'Producción'),
        ],
        string='Ambiente Webservices ARCA/AFIP',
        default='testing',
    )
    l10n_ar_afip_ws_crt_id = fields.Many2one(
        'certificate.certificate',
        string='Certificado ARCA/AFIP (X.509)',
        domain="[('company_id', 'in', [id, False])]",
    )
    l10n_ar_afip_ws_key_id = fields.Many2one(
        'certificate.key',
        string='Clave Privada ARCA/AFIP',
        domain="[('company_id', 'in', [id, False])]",
    )
    l10n_ar_afip_verification_type = fields.Selection(
        selection=[
            ('not_available', 'No disponible'),
            ('available', 'Disponible (Opcional)'),
            ('required', 'Requerido'),
        ],
        string='Verificación de Comprobantes en ARCA',
        default='available',
    )
    l10n_ar_fce_transmission_type = fields.Selection(
        selection=[
            ('SCA', 'SCA - Sistema de Circulación Abierta'),
            ('ADC', 'ADC - Agente de Depósito Colectivo'),
        ],
        string='Opción de Transmisión FCE (MiPyME)',
        default='SCA',
    )
    l10n_ar_computable_tax_credit = fields.Selection(
        selection=[
            ('global', 'Prorrateo Global'),
            ('direct', 'Asignación Directa en Comprobante'),
        ],
        string='Crédito Fiscal Computable (Libro IVA Digital)',
        default='direct',
    )
    l10n_ar_daily_book_start_entry_number = fields.Integer(
        string='Número Inicial de Asiento en Libro Diario',
        default=1,
    )
    l10n_ar_caea_contingency_until = fields.Datetime(
        string='Contingencia CAEA activa hasta',
        copy=False,
        help='Mientras ARCA no responde, los comprobantes de diarios con punto de venta de '
             'contingencia se emiten directamente con CAEA hasta esta hora, sin esperar al servicio.',
    )
    l10n_ar_connection_ids = fields.One2many(
        'l10n_ar.afipws.connection',
        'company_id',
        string='Conexiones Webservice ARCA/AFIP',
    )

    def _l10n_ar_notification(self, title, message, kind='success', sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': sticky},
        }

    def action_l10n_ar_test_afip_connection(self):
        """Pide (o reutiliza) el ticket WSAA de facturación y consulta el último comprobante."""
        self.ensure_one()
        env_label = _('Producción') if self.l10n_ar_afip_ws_environment == 'production' else _('Homologación')
        try:
            conn = self.env['l10n_ar.afipws.connection'].get_active_connection(self, 'wsfe')
        except UserError as error:
            return self._l10n_ar_notification(
                _('Facturación ARCA: no se pudo conectar'), str(error), 'danger', sticky=True)
        expiration = fields.Datetime.context_timestamp(self, conn.expiration_time) if conn.expiration_time else False
        return self._l10n_ar_notification(
            _('Facturación ARCA: conexión correcta'),
            _('%(company)s (%(env)s): ARCA aceptó el certificado para facturación electrónica. Ticket vigente hasta %(exp)s.',
              company=self.name, env=env_label,
              exp=expiration.strftime('%d/%m/%Y %H:%M') if expiration else '-'),
        )

    def action_l10n_ar_test_padron_connection(self):
        """Consulta en el padrón el propio CUIT de la empresa representada."""
        self.ensure_one()
        partner_model = self.env['res.partner']
        try:
            shared = self.env['res.config.settings']._get_dolan_padron_configuration()
            company = shared['representative_company'] if shared else self
            cuit = shared['represented_cuit'] if shared else ''.join(c for c in (self.vat or '') if c.isdigit())
            if not partner_model._l10n_ar_validate_cuit_checksum(cuit):
                raise UserError(_('Configurá un CUIT válido en la empresa "%s".') % company.name)
            data = partner_model.new({'vat': cuit})._l10n_ar_fetch_padron_data(cuit)
        except UserError as error:
            return self._l10n_ar_notification(
                _('Padrón ARCA: no se pudo consultar'), str(error), 'danger', sticky=True)
        return self._l10n_ar_notification(
            _('Padrón ARCA: conexión correcta'),
            _('Consulta de prueba con el certificado de %(company)s: CUIT %(cuit)s = %(name)s.',
              company=company.name, cuit=cuit, name=data.get('name') or '-'),
        )

    def action_l10n_ar_generate_csr(self):
        """Compatibilidad: abre un pedido de certificado nuevo para la empresa."""
        self.ensure_one()
        return self.env['res.config.settings']._l10n_ar_arca_open_new_request(self)

    CAEA_CONTINGENCY_MINUTES = 5

    def _l10n_ar_caea_contingency_active(self):
        self.ensure_one()
        until = self.sudo().l10n_ar_caea_contingency_until
        return bool(until and until > fields.Datetime.now())

    def _l10n_ar_caea_mark_unavailable(self):
        for company in self:
            if not company._l10n_ar_caea_contingency_active():
                company.l10n_ar_caea_contingency_until = (
                    fields.Datetime.now() + timedelta(minutes=self.CAEA_CONTINGENCY_MINUTES)
                )
