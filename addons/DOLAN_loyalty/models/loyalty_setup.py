from odoo import Command, _, fields, models
from odoo.exceptions import UserError


class DolanLoyaltySetup(models.TransientModel):
    _name = 'dolan.loyalty.setup'
    _description = 'Configurar fidelización'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    program_name = fields.Char('Nombre del programa', required=True, default='Club de puntos')
    pesos_per_point = fields.Monetary('Pesos de compra por punto', required=True, default=1000,
                                      help='Cada cuántos pesos pagados el cliente gana un punto.')
    point_value = fields.Monetary('Valor de un punto al canjear', required=True, default=10,
                                  help='Descuento en pesos por cada punto canjeado.')
    min_points = fields.Integer('Mínimo de puntos para canjear', required=True, default=100)
    validity_days = fields.Integer('Los puntos vencen a los (días)', default=365,
                                   help='0 = los puntos no vencen.')
    create_gift_card = fields.Boolean('Crear también la tarjeta de regalo', default=True)

    def _check_values(self):
        if self.pesos_per_point <= 0 or self.point_value <= 0:
            raise UserError(_('Los pesos por punto y el valor del punto tienen que ser mayores que cero.'))
        if self.min_points < 1:
            raise UserError(_('El mínimo para canjear tiene que ser de al menos 1 punto.'))
        if self.validity_days < 0:
            raise UserError(_('El vencimiento no puede ser negativo.'))

    def _points_program_vals(self):
        return {
            'name': self.program_name,
            'program_type': 'loyalty',
            'company_id': self.company_id.id,
            'applies_on': 'future',
            'trigger': 'auto',
            'portal_visible': True,
            'portal_point_name': _('Puntos'),
            'expire_after': self.validity_days,
            'rule_ids': [Command.clear(), Command.create({
                'reward_point_mode': 'money',
                'reward_point_amount': 1 / self.pesos_per_point,
            })],
            'reward_ids': [Command.clear(), Command.create({
                'reward_type': 'discount',
                'discount_mode': 'per_point',
                'discount': self.point_value,
                'discount_applicability': 'order',
                'required_points': self.min_points,
            })],
            'communication_plan_ids': [Command.clear()],
        }

    def action_create(self):
        self.ensure_one()
        self._check_values()
        Program = self.env['loyalty.program'].with_company(self.company_id)
        program = Program.create(self._points_program_vals())
        programs = program
        if self.create_gift_card:
            templates = Program._get_template_values()
            if 'gift_card' in templates:
                programs |= Program.create(dict(templates['gift_card'], name=_('Tarjeta de regalo'),
                                                company_id=self.company_id.id))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Programas creados'),
            'res_model': 'loyalty.program',
            'view_mode': 'list,form',
            'domain': [('id', 'in', programs.ids)],
        }
