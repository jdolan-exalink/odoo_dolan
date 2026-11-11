# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Points of sale numbered by DOLAN that report through WSFEv1: the regular CAE
# point of sale and the dedicated CAEA contingency point of sale (RG 5782/2025).
DOLAN_WSFE_POS_SYSTEMS = ('DOLAN_WSFE', 'DOLAN_CAEA')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_ar_afip_ws = fields.Selection(
        selection=[
            ('wsfe', 'Mercado interno -sin detalle- RG2485 (WSFEv1)'),
            ('wsfex', 'Exportación -con detalle- RG2758 (WSFEXv1)'),
            ('wsmtxca', 'Mercado interno -con detalle- RG2904 (WSMTXCA)'),
        ],
        string='Webservice ARCA/AFIP',
        compute='_compute_l10n_ar_afip_ws',
        store=True,
        readonly=False,
    )
    l10n_ar_caea_journal_id = fields.Many2one(
        'account.journal',
        string='Punto de venta de contingencia (CAEA)',
        domain="[('company_id', '=', company_id), ('type', '=', 'sale'), ('l10n_ar_afip_pos_system', '=', 'DOLAN_CAEA')]",
        check_company=True,
        help='Si ARCA no responde al pedir el CAE, el comprobante se emite en este punto de venta '
             'con el CAEA vigente y se informa a ARCA cuando vuelve el servicio.',
    )

    def _get_l10n_ar_afip_pos_types_selection(self):
        return super()._get_l10n_ar_afip_pos_types_selection() + [
            ('DOLAN_WSFE', 'Webservice WSFEv1'),
            ('DOLAN_CAEA', 'Webservice WSFEv1 - CAEA (contingencia)'),
        ]

    @api.model
    def _get_codes_per_journal_type(self, afip_pos_system):
        if afip_pos_system in DOLAN_WSFE_POS_SYSTEMS and self.type == 'sale':
            # Same documents WSFEv1 authorizes: A/B/C/M invoices and notes,
            # receipts and MiPyME FCE.
            return super()._get_codes_per_journal_type('RAW_MAW')
        return super()._get_codes_per_journal_type(afip_pos_system)

    @api.depends('l10n_ar_afip_pos_system', 'type')
    def _compute_l10n_ar_afip_ws(self):
        for journal in self:
            # Preprinted, online portal and fiscal-controller journals are native
            # circuits, not an implicit authorization to invoke a web service.
            journal.l10n_ar_afip_ws = (
                'wsfe'
                if journal.type == 'sale' and journal.l10n_ar_afip_pos_system in DOLAN_WSFE_POS_SYSTEMS
                else False
            )

    @api.constrains('l10n_ar_caea_journal_id', 'l10n_ar_afip_pos_system', 'l10n_ar_afip_pos_number')
    def _check_l10n_ar_caea_journal(self):
        # Changing the contingency journal itself must re-check its CAE journals.
        referencing = self.search([('l10n_ar_caea_journal_id', 'in', self.ids)]) if self.ids else self.browse()
        for journal in self | referencing:
            contingency = journal.l10n_ar_caea_journal_id
            if not contingency:
                continue
            if journal.l10n_ar_afip_pos_system != 'DOLAN_WSFE':
                raise ValidationError(_('Solo un diario WSFEv1 (CAE) puede tener punto de venta de contingencia CAEA.'))
            if contingency.l10n_ar_afip_pos_system != 'DOLAN_CAEA' or contingency.type != 'sale':
                raise ValidationError(_('El diario de contingencia debe ser de ventas con sistema CAEA.'))
            if contingency.l10n_ar_afip_pos_number == journal.l10n_ar_afip_pos_number:
                raise ValidationError(_('ARCA exige un punto de venta exclusivo para CAEA, distinto del de CAE.'))
