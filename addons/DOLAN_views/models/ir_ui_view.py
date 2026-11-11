# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(
        selection_add=[
            ('dolan_gantt', 'Gantt'),
            ('dolan_cohort', 'Cohorte'),
            ('dolan_grid', 'Grilla'),
            ('dolan_map', 'Mapa'),
        ],
        ondelete={
            'dolan_gantt': 'cascade',
            'dolan_cohort': 'cascade',
            'dolan_grid': 'cascade',
            'dolan_map': 'cascade',
        },
    )


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(
        selection_add=[
            ('dolan_gantt', 'Gantt'),
            ('dolan_cohort', 'Cohorte'),
            ('dolan_grid', 'Grilla'),
            ('dolan_map', 'Mapa'),
        ],
        ondelete={
            'dolan_gantt': 'cascade',
            'dolan_cohort': 'cascade',
            'dolan_grid': 'cascade',
            'dolan_map': 'cascade',
        },
    )
