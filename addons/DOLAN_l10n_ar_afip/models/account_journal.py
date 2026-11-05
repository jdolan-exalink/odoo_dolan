# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import api, fields, models


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

    def _get_l10n_ar_afip_pos_types_selection(self):
        return super()._get_l10n_ar_afip_pos_types_selection() + [
            ('DOLAN_WSFE', 'Webservice WSFEv1 (DOLAN)'),
        ]

    @api.depends('l10n_ar_afip_pos_system', 'type')
    def _compute_l10n_ar_afip_ws(self):
        for journal in self:
            # Preprinted, online portal and fiscal-controller journals are native
            # circuits, not an implicit authorization to invoke a web service.
            journal.l10n_ar_afip_ws = (
                'wsfe' if journal.type == 'sale' and journal.l10n_ar_afip_pos_system == 'DOLAN_WSFE' else False
            )
