# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Percepciones y retenciones de Ingresos Brutos según padrón provincial.

Cada compañía configura en qué jurisdicciones es agente de percepción (ventas)
o de retención (pagos). Con el padrón importado (``dolan.iibb.padron``):

* las facturas de cliente reciben, al publicarse, la percepción con la alícuota
  del padrón vigente a la fecha del comprobante (tributo ARCA 07);
* los proveedores quedan inscriptos en los regímenes de retención de
  ``l10n_ar_withholding`` (``l10n_ar.partner.tax``) con la alícuota del padrón,
  así el asistente de pago propone la retención sola.
"""

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PADRON_JURISDICTIONS = [
    ('arba', 'ARBA - Provincia de Buenos Aires'),
    ('agip', 'AGIP - CABA'),
    ('cordoba', 'Rentas Córdoba'),
    ('santa_fe', 'API Santa Fe'),
    ('tucuman', 'Rentas Tucumán'),
    ('mendoza', 'ATM Mendoza'),
    ('sircar', 'SIRCAR / Convenio Multilateral'),
    ('sircreb', 'SIRCREB (recaudación bancaria)'),
]

# Jurisdiction -> ISO 3166-2 code of the Argentine province it belongs to.
JURISDICTION_STATE_CODES = {
    'arba': 'B',
    'agip': 'C',
    'cordoba': 'X',
    'santa_fe': 'S',
    'tucuman': 'T',
    'mendoza': 'M',
}

ARCA_TRIBUTE_IIBB_PERCEPTION = '07'


class DolanArTaxJurisdiction(models.Model):
    _name = 'dolan.ar.tax.jurisdiction'
    _description = 'Jurisdicción IIBB: agente de percepción y retención por padrón'
    _order = 'company_id, jurisdiction'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company, index=True,
    )
    jurisdiction = fields.Selection(PADRON_JURISDICTIONS, string='Jurisdicción', required=True)
    state_id = fields.Many2one(
        'res.country.state', string='Provincia',
        compute='_compute_state_id', store=True, readonly=False,
        domain="[('country_id.code', '=', 'AR')]",
    )
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    perception_active = fields.Boolean(string='Agente de percepción')
    perception_account_id = fields.Many2one(
        'account.account', string='Cuenta de percepciones a pagar', check_company=True,
    )
    perception_min_base = fields.Monetary(
        string='Base mínima para percibir',
        help='Por debajo de este neto gravado no se aplica la percepción.',
    )
    perception_only_local = fields.Boolean(
        string='Solo clientes con domicilio en la provincia',
        help='Si se marca, se percibe solo a clientes cuya dirección está en esta provincia.',
    )
    withholding_active = fields.Boolean(string='Agente de retención')
    withholding_account_id = fields.Many2one(
        'account.account', string='Cuenta de retenciones a pagar', check_company=True,
    )
    withholding_minimum_amount = fields.Float(
        string='Retención mínima',
        digits='Account',
        help='Si la retención calculada es menor, no se retiene.',
    )
    withholding_non_taxable_amount = fields.Float(
        string='Monto no sujeto a retención',
        digits='Account',
        help='Hasta esta base no se retiene.',
    )
    tax_ids = fields.One2many('account.tax', 'dolan_padron_jurisdiction_id', string='Impuestos generados', readonly=True)

    _company_jurisdiction_unique = models.Constraint(
        'unique(company_id, jurisdiction)',
        'La jurisdicción ya está configurada para esta compañía.',
    )

    @api.depends('jurisdiction')
    def _compute_state_id(self):
        for record in self:
            code = JURISDICTION_STATE_CODES.get(record.jurisdiction)
            record.state_id = code and self.env['res.country.state'].search([
                ('country_id.code', '=', 'AR'), ('code', '=', code),
            ], limit=1)

    @api.constrains('perception_active', 'perception_account_id', 'withholding_active', 'withholding_account_id')
    def _check_accounts(self):
        for record in self:
            if record.perception_active and not record.perception_account_id:
                raise ValidationError(_('Configure la cuenta de percepciones de %s.') % record.display_name)
            if record.withholding_active and not record.withholding_account_id:
                raise ValidationError(_('Configure la cuenta de retenciones de %s.') % record.display_name)

    @api.depends('jurisdiction', 'company_id')
    def _compute_display_name(self):
        labels = dict(PADRON_JURISDICTIONS)
        for record in self:
            record.display_name = labels.get(record.jurisdiction, record.jurisdiction or '')

    # ------------------------------------------------------------------
    # Taxes per aliquot
    # ------------------------------------------------------------------
    def _label(self):
        return dict(PADRON_JURISDICTIONS).get(self.jurisdiction, self.jurisdiction).split(' - ')[0].split(' (')[0]

    def _get_tax_group(self, kind):
        self.ensure_one()
        name = (_('Percepción IIBB %s') if kind == 'perception' else _('Retención IIBB %s')) % self._label()
        Group = self.env['account.tax.group'].sudo()
        group = Group.search([('name', '=', name), ('company_id', '=', self.company_id.id)], limit=1)
        if not group:
            values = {'name': name, 'company_id': self.company_id.id, 'country_id': self.env.ref('base.ar').id}
            if kind == 'perception':
                values['l10n_ar_tribute_afip_code'] = ARCA_TRIBUTE_IIBB_PERCEPTION
            group = Group.create(values)
        return group

    def _repartition(self, account):
        return [
            Command.create({'repartition_type': 'base', 'document_type': 'invoice'}),
            Command.create({'repartition_type': 'tax', 'document_type': 'invoice', 'account_id': account.id}),
            Command.create({'repartition_type': 'base', 'document_type': 'refund'}),
            Command.create({'repartition_type': 'tax', 'document_type': 'refund', 'account_id': account.id}),
        ]

    def _get_perception_tax(self, aliquot):
        """Sale tax for this jurisdiction and aliquot, created on first use."""
        self.ensure_one()
        aliquot = round(aliquot, 4)
        Tax = self.env['account.tax'].sudo().with_context(active_test=False)
        tax = Tax.search([
            ('dolan_padron_jurisdiction_id', '=', self.id),
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', aliquot),
        ], limit=1)
        if tax:
            if not tax.active:
                tax.active = True
            return tax
        return Tax.create({
            'name': _('Percepción IIBB %(jur)s %(rate)s%%', jur=self._label(), rate=f'{aliquot:g}'),
            'company_id': self.company_id.id,
            'country_id': self.env.ref('base.ar').id,
            'type_tax_use': 'sale',
            'amount_type': 'percent',
            'amount': aliquot,
            'sequence': 50,
            'tax_group_id': self._get_tax_group('perception').id,
            'dolan_padron_jurisdiction_id': self.id,
            'invoice_repartition_line_ids': self._repartition(self.perception_account_id)[:2],
            'refund_repartition_line_ids': self._repartition(self.perception_account_id)[2:],
        })

    def _get_withholding_tax(self, aliquot):
        """Payment withholding tax (l10n_ar_withholding) for this jurisdiction and aliquot."""
        self.ensure_one()
        aliquot = round(aliquot, 4)
        Tax = self.env['account.tax'].sudo().with_context(active_test=False)
        tax = Tax.search([
            ('dolan_padron_jurisdiction_id', '=', self.id),
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', aliquot),
        ], limit=1)
        values = {
            'l10n_ar_minimum_threshold': self.withholding_minimum_amount,
            'l10n_ar_non_taxable_amount': self.withholding_non_taxable_amount,
        }
        if tax:
            tax.write(dict(values, active=True))
            return tax
        return Tax.create(dict(
            values,
            name=_('Retención IIBB %(jur)s %(rate)s%%', jur=self._label(), rate=f'{aliquot:g}'),
            company_id=self.company_id.id,
            country_id=self.env.ref('base.ar').id,
            type_tax_use='purchase',
            amount_type='percent',
            amount=aliquot,
            is_withholding_tax=True,
            l10n_ar_withholding_tax_type='iibb_untaxed',
            l10n_ar_state_id=self.state_id.id,
            tax_group_id=self._get_tax_group('withholding').id,
            dolan_padron_jurisdiction_id=self.id,
            invoice_repartition_line_ids=self._repartition(self.withholding_account_id)[:2],
            refund_repartition_line_ids=self._repartition(self.withholding_account_id)[2:],
        ))

    # ------------------------------------------------------------------
    # Padron lookups
    # ------------------------------------------------------------------
    def _padron_record(self, partner, date):
        self.ensure_one()
        cuit = ''.join(char for char in (partner.commercial_partner_id.vat or '') if char.isdigit())
        if len(cuit) != 11:
            return self.env['dolan.iibb.padron']
        return self.env['dolan.iibb.padron'].sudo().search([
            ('vat', '=', cuit),
            ('jurisdiction', '=', self.jurisdiction),
            ('from_date', '<=', date),
            ('to_date', '>=', date),
        ], order='from_date desc, id desc', limit=1)

    # ------------------------------------------------------------------
    # Withholding regimes sync
    # ------------------------------------------------------------------
    def action_sync_withholding_regimes(self):
        """Register suppliers found in the padrón in the withholding regimes.

        Creates one ``l10n_ar.partner.tax`` per supplier and padrón period, with
        the tax of the padrón aliquot, so Odoo's payment wizard proposes it.
        """
        PartnerTax = self.env['l10n_ar.partner.tax'].sudo()
        created = 0
        for record in self.filtered(lambda r: r.withholding_active and r.active):
            company = record.company_id
            suppliers = self.env['res.partner'].sudo().search([
                ('supplier_rank', '>', 0),
                ('vat', '!=', False),
                ('parent_id', '=', False),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ])
            by_cuit = {}
            for supplier in suppliers:
                cuit = ''.join(char for char in supplier.vat if char.isdigit())
                if len(cuit) == 11:
                    by_cuit.setdefault(cuit, supplier)
            if not by_cuit:
                continue
            rows = self.env['dolan.iibb.padron'].sudo().search([
                ('jurisdiction', '=', record.jurisdiction),
                ('vat', 'in', list(by_cuit)),
                ('to_date', '>=', fields.Date.context_today(self)),
            ])
            managed_taxes = record.with_context(active_test=False).tax_ids.filtered(
                lambda t: t.type_tax_use == 'purchase'
            )
            for row in rows:
                partner = by_cuit[row.vat]
                existing = PartnerTax.search([
                    ('partner_id', '=', partner.id),
                    ('tax_id', 'in', managed_taxes.ids),
                    ('from_date', '=', row.from_date),
                ])
                if row.withholding_aliquot <= 0:
                    existing.unlink()
                    continue
                tax = record._get_withholding_tax(row.withholding_aliquot)
                managed_taxes |= tax
                values = {'tax_id': tax.id, 'to_date': row.to_date, 'ref': _('Padrón %s') % record._label()}
                if existing:
                    existing[:1].write(values)
                    (existing - existing[:1]).unlink()
                else:
                    PartnerTax.create(dict(values, partner_id=partner.id, from_date=row.from_date))
                    created += 1
        return created

    @api.model
    def _cron_sync_withholding_regimes(self):
        self.search([('withholding_active', '=', True)]).action_sync_withholding_regimes()


class AccountTax(models.Model):
    _inherit = 'account.tax'

    dolan_padron_jurisdiction_id = fields.Many2one(
        'dolan.ar.tax.jurisdiction',
        string='Jurisdicción de padrón',
        index='btree_not_null',
        ondelete='set null',
        readonly=True,
        help='Impuesto creado y administrado automáticamente según el padrón de IIBB.',
    )


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dolan_iibb_perception_exempt = fields.Boolean(
        string='Exento de percepciones IIBB',
        help='No aplicar percepciones de padrón a este cliente (por ejemplo, con certificado de exclusión).',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _dolan_padron_perception_jurisdictions(self):
        return self.env['dolan.ar.tax.jurisdiction'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('perception_active', '=', True),
        ])

    def action_dolan_apply_padron_perceptions(self):
        """Set IIBB perceptions on customer documents from the padrón in force."""
        for move in self:
            if (
                move.state != 'draft'
                or move.move_type not in ('out_invoice', 'out_refund')
                or move.country_code != 'AR'
                or (move.move_type == 'out_refund' and move.reversed_entry_id)
            ):
                # Credit notes keep the perceptions copied from the invoice they reverse.
                continue
            jurisdictions = move._dolan_padron_perception_jurisdictions()
            if not jurisdictions:
                continue
            lines = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
            managed = lines.tax_ids.filtered(lambda tax: tax.dolan_padron_jurisdiction_id in jurisdictions)
            partner = move.commercial_partner_id
            date = move.invoice_date or fields.Date.context_today(move)
            wanted = self.env['account.tax']
            letter = move.l10n_latam_document_type_id.l10n_ar_letter
            if not partner.dolan_iibb_perception_exempt and letter not in ('E', 'C'):
                net = sum(lines.mapped('price_subtotal'))
                for jurisdiction in jurisdictions:
                    if jurisdiction.perception_only_local and partner.state_id != jurisdiction.state_id:
                        continue
                    if move.currency_id.compare_amounts(abs(net), jurisdiction.perception_min_base) < 0:
                        continue
                    row = jurisdiction._padron_record(partner, date)
                    if row and row.perception_aliquot > 0:
                        wanted |= jurisdiction._get_perception_tax(row.perception_aliquot)
            if managed == wanted and all(wanted <= line.tax_ids for line in lines):
                continue
            for line in lines:
                line.tax_ids = [Command.unlink(tax.id) for tax in line.tax_ids & managed] + [
                    Command.link(tax.id) for tax in wanted
                ]
        return True

    def _post(self, soft=True):
        self.filtered(
            lambda m: m.state == 'draft' and m.move_type in ('out_invoice', 'out_refund') and m.country_code == 'AR'
        ).action_dolan_apply_padron_perceptions()
        return super()._post(soft=soft)
