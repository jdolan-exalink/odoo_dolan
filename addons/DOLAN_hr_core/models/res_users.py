# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def action_dolan_link_employee(self):
        """Abre el asistente que vincula el usuario con su ficha en la compañía actual."""
        self.ensure_one()
        wizard = self.env['dolan.hr.link.user.employee'].create({'user_id': self.id})
        return wizard._action_open()

    def dolan_employee_or_guide(self, company=None):
        """Devuelve ``(empleado, acción)``: el empleado del usuario en la compañía,
        o una acción que explica cómo vincularlo.

        Los módulos de Personal (vacaciones, fichadas, portal) lo usan para
        mostrar una guía en lugar de un error de acceso cuando falta el vínculo.
        """
        self.ensure_one()
        company = company or self.env.company
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', self.id), ('company_id', '=', company.id),
        ], limit=1)
        if employee:
            return employee, False
        if self.env.user.has_group('hr.group_hr_user'):
            return employee, self.action_dolan_link_employee()
        return employee, {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tu usuario no tiene ficha de empleado'),
                'message': _('Pedile a Recursos Humanos que vincule tu usuario con tu legajo en %s. '
                             'Hasta entonces no vas a ver turnos, fichadas ni recibos.', company.name),
                'type': 'warning',
                'sticky': True,
            },
        }
