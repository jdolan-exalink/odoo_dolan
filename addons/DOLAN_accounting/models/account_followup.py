# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import _, api, fields, models


class DolanFollowupLevel(models.Model):
    _name = 'dolan.followup.level'
    _description = 'Nivel de Seguimiento de Deudores y Cobranzas'
    _order = 'delay_days asc, id asc'

    name = fields.Char(string='Nombre del Nivel', required=True)
    delay_days = fields.Integer(
        string='Días de Mora después del Vencimiento',
        required=True,
        default=15,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    send_email = fields.Boolean(string='Enviar Recordatorio por Email', default=True)
    block_sales = fields.Boolean(string='Sugerir Bloqueo Comercial', default=False)
    message_template = fields.Text(
        string='Plantilla de Mensaje de Reclamo',
        default=lambda self: _(
            "Estimado cliente,\nLe recordamos que registra comprobantes vencidos pendientes de cancelación. "
            "Le solicitamos regularizar su cuenta corriente a la brevedad."
        ),
    )


class ResPartnerFollowup(models.Model):
    _inherit = 'res.partner'

    dolan_overdue_amount = fields.Monetary(
        string='Deuda Vencida Exigible',
        compute='_compute_dolan_followup_status',
        currency_field='currency_id',
    )
    dolan_max_overdue_days = fields.Integer(
        string='Máximo Días de Mora',
        compute='_compute_dolan_followup_status',
    )
    dolan_followup_level_id = fields.Many2one(
        'dolan.followup.level',
        string='Nivel de Reclamo Actual',
        compute='_compute_dolan_followup_status',
    )
    dolan_last_followup_date = fields.Date(
        string='Fecha Último Reclamo de Cobranza',
        copy=False,
    )
    dolan_credit_blocked = fields.Boolean(
        string='Bloqueado por Mora',
        default=False,
    )

    def _compute_dolan_followup_status(self):
        today = fields.Date.context_today(self)
        levels = self.env['dolan.followup.level'].search([], order='delay_days desc')
        for partner in self:
            overdue_moves = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', today),
            ])
            total_overdue = sum(overdue_moves.mapped('amount_residual'))
            max_days = 0
            for move in overdue_moves:
                if move.invoice_date_due:
                    days = (today - move.invoice_date_due).days
                    if days > max_days:
                        max_days = days

            matched_level = False
            if total_overdue > 0 and max_days > 0:
                for lvl in levels:
                    if max_days >= lvl.delay_days:
                        matched_level = lvl
                        break

            partner.dolan_overdue_amount = total_overdue
            partner.dolan_max_overdue_days = max_days
            partner.dolan_followup_level_id = matched_level

    def action_dolan_send_followup_statement(self):
        """Registra el envío del estado de cuenta corriente en el chatter del cliente."""
        today = fields.Date.context_today(self)
        for partner in self:
            lvl = partner.dolan_followup_level_id
            msg_body = (
                lvl.message_template
                if lvl
                else _("Se envió el estado de cuenta corriente actualizado al cliente.")
            )
            partner.message_post(
                body=_(
                    "<strong>Seguimiento de Cobranzas:</strong><br/>"
                    "Deuda Vencida: $ %(amt).2f | Mora máxima: %(days)d días<br/>"
                    "<p>%(msg)s</p>",
                    amt=partner.dolan_overdue_amount,
                    days=partner.dolan_max_overdue_days,
                    msg=msg_body,
                ),
                subject=_("Estado de Cuenta Corriente - %s") % partner.display_name,
            )
            vals = {'dolan_last_followup_date': today}
            if lvl and lvl.block_sales:
                vals['dolan_credit_blocked'] = True
            partner.write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Estado de Cuenta Enviado'),
                'message': _('Se registró y notificó el seguimiento de cuenta corriente.'),
                'type': 'success',
                'sticky': False,
            },
        }
