# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
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

    def action_l10n_ar_test_afip_connection(self):
        """Prueba la conexión WSAA para la compañía actual."""
        self.ensure_one()
        conn = self.env['l10n_ar.afipws.connection'].get_active_connection(self, 'wsfe')
        mode_msg = (
            _("Modo Simulación de Homologación activo (sin certificado X.509 cargado)")
            if conn.is_simulated
            else _("Certificado X.509 validado contra WSAA")
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión ARCA/AFIP Exitosa'),
                'message': _(
                    'Ambiente: %(env)s | Servicio: %(ws)s | Vence: %(exp)s (%(mode)s)',
                    env=conn.type,
                    ws=conn.l10n_ar_afip_ws,
                    exp=conn.expiration_time,
                    mode=mode_msg,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_l10n_ar_generate_csr(self):
        """Genera una solicitud de certificado (CSR) y clave privada RSA 2048 para subir al portal de ARCA."""
        self.ensure_one()
        cuit = (self.vat or '').replace('-', '').replace(' ', '') or '20000000001'
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID

            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.name or "Empresa Argentina"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"DOLAN_Odoo20_{cuit}"),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}"),
            ])
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(subject)
                .sign(private_key, hashes.SHA256())
            )
            csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        except Exception as exc:
            raise UserError(_("No se pudo generar el CSR X.509: %s") % exc)

        if not self.l10n_ar_afip_ws_key_id:
            key_rec = self.env['certificate.key'].create({
                'name': f"Clave Privada ARCA {self.name} ({cuit})",
                'content': base64.b64encode(key_pem),
                'company_id': self.id,
            })
            self.l10n_ar_afip_ws_key_id = key_rec.id

        attachment = self.env['ir.attachment'].create({
            'name': f"ARCA_CSR_{cuit}.csr",
            'type': 'binary',
            'datas': base64.b64encode(csr_pem),
            'mimetype': 'application/pkcs10',
            'res_model': 'res.company',
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

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
