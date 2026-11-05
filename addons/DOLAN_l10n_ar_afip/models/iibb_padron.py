# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DolanIibbPadron(models.Model):
    _name = 'dolan.iibb.padron'
    _description = 'Padrón Provincial de Alícuotas IIBB (ARBA / AGIP / Provincias)'
    _order = 'to_date desc, vat asc'

    vat = fields.Char(
        string='CUIT / CUIL',
        required=True,
        index=True,
        help='Identificador fiscal sin guiones (11 dígitos).',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto Asociado',
        compute='_compute_partner_id',
        store=True,
    )
    jurisdiction = fields.Selection([
        ('arba', 'ARBA - Provincia de Buenos Aires'),
        ('agip', 'AGIP - CABA'),
        ('cordoba', 'Rentas Córdoba'),
        ('santa_fe', 'API Santa Fe'),
        ('sircar', 'SIRCAR / Convenio Multilateral'),
    ], string='Jurisdicción', required=True, default='arba', index=True)

    from_date = fields.Date(string='Vigencia Desde', required=True)
    to_date = fields.Date(string='Vigencia Hasta', required=True)

    perception_aliquot = fields.Float(
        string='Alícuota Percepción (%)',
        digits=(5, 2),
        default=0.0,
        help='Porcentaje a aplicar en facturas de venta como percepción de IIBB.',
    )
    withholding_aliquot = fields.Float(
        string='Alícuota Retención (%)',
        digits=(5, 2),
        default=0.0,
        help='Porcentaje a aplicar en órdenes de pago como retención de IIBB.',
    )
    regime_code = fields.Char(string='Código de Régimen / Grupo')

    @api.depends('vat')
    def _compute_partner_id(self):
        for rec in self:
            if rec.vat:
                partner = self.env['res.partner'].search([('vat', '=', rec.vat)], limit=1)
                rec.partner_id = partner.id if partner else False
            else:
                rec.partner_id = False


class ResPartner(models.Model):
    _inherit = 'res.partner'

    iibb_padron_ids = fields.One2many(
        'dolan.iibb.padron',
        'partner_id',
        string='Historial en Padrones IIBB',
        readonly=True,
    )

    def get_iibb_aliquots(self, jurisdiction='arba', target_date=None):
        """Retorna (alicuota_percepcion, alicuota_retencion) vigentes para la fecha especificada."""
        self.ensure_one()
        cuit = ''.join(c for c in (self.vat or '') if c.isdigit())
        if not cuit or len(cuit) != 11:
            return 0.0, 0.0

        eval_date = target_date or fields.Date.today()
        record = self.env['dolan.iibb.padron'].search([
            ('vat', '=', cuit),
            ('jurisdiction', '=', jurisdiction),
            ('from_date', '<=', eval_date),
            ('to_date', '>=', eval_date),
        ], order='to_date desc', limit=1)

        if record:
            return record.perception_aliquot, record.withholding_aliquot
        return 0.0, 0.0


class DolanRetentionCertificate(models.Model):
    _name = 'dolan.retention.certificate'
    _description = 'Certificado de Retención Impositiva (Ganancias, IVA, IIBB)'
    _order = 'date desc, name desc'

    name = fields.Char(
        string='Número de Certificado',
        required=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('dolan.retention.cert') or _('Nuevo'),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía Emisora',
        required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Sujeto Retenido (Proveedor)',
        required=True,
    )
    partner_vat = fields.Char(
        string='CUIT Sujeto Retenido',
        related='partner_id.vat',
    )
    date = fields.Date(
        string='Fecha de Retención',
        required=True,
        default=fields.Date.context_today,
    )
    tax_type = fields.Selection([
        ('ganancias', 'Impuesto a las Ganancias (RG 830)'),
        ('iva', 'Impuesto al Valor Agregado (RG 1575 / 4621)'),
        ('iibb_arba', 'Ingresos Brutos ARBA (Provincia Bs As)'),
        ('iibb_agip', 'Ingresos Brutos AGIP (CABA)'),
        ('suss', 'Seguridad Social (SUSS)'),
    ], string='Régimen de Retención', required=True, default='ganancias')

    base_amount = fields.Monetary(string='Base Imponible', required=True, currency_field='currency_id')
    aliquot = fields.Float(string='Alícuota Aplicada (%)', digits=(5, 2), required=True)
    amount = fields.Monetary(string='Importe Retenido', required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    payment_id = fields.Many2one('account.payment', string='Pago Asociado')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Emitido'),
        ('annulled', 'Anulado'),
    ], default='confirmed', string='Estado')

    def generate_sicore_line(self):
        """Genera una línea estándar en formato posicional para el aplicativo SICORE / SIRE de ARCA."""
        self.ensure_one()
        # Código de comprobante retenido (01=Factura), Fecha, CUIT agente, CUIT retenido, Base, Alícuota, Importe
        cuit_agente = ''.join(c for c in (self.company_id.vat or '') if c.isdigit()).zfill(11)
        cuit_retenido = ''.join(c for c in (self.partner_vat or '') if c.isdigit()).zfill(11)
        fecha_str = self.date.strftime('%d/%m/%Y')
        imp_base = f"{abs(self.base_amount):014.2f}".replace('.', ',')
        imp_ret = f"{abs(self.amount):014.2f}".replace('.', ',')
        alic = f"{self.aliquot:05.2f}".replace('.', ',')

        # Formato SICORE estándar:
        # CodComprobante(2) + Fecha(10) + NroComprobante(16) + Base(14) + CodImpuesto(4) + CodRegimen(3) + Alic(5) + Retenido(14)
        cod_imp = '217' if self.tax_type == 'ganancias' else '767' # 217=Ganancias, 767=IVA
        return f"01{fecha_str}{self.name[:16].ljust(16)}{imp_base}{cod_imp}001{alic}{imp_ret}\r\n"
