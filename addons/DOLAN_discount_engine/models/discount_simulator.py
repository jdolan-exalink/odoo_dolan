import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DolanDiscountSimulator(models.TransientModel):
    _name = 'dolan.discount.simulator'
    _description = 'Simulador de promociones'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    pos_config_id = fields.Many2one('pos.config', required=True, domain="[('company_id', '=', company_id)]")
    at = fields.Datetime(required=True, default=fields.Datetime.now)
    product_id = fields.Many2one('product.product', required=True)
    quantity = fields.Float(required=True, default=1.0, digits='Product Unit')
    unit_price = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    payment_method_id = fields.Many2one('pos.payment.method', string='Medio de pago (solo informativo)', check_company=True)
    result = fields.Text(readonly=True)

    @api.constrains('pos_config_id', 'company_id', 'quantity', 'unit_price')
    def _check_simulator_scope(self):
        for wizard in self:
            if wizard.pos_config_id.company_id != wizard.company_id:
                raise ValidationError(_('La caja debe pertenecer a la empresa seleccionada.'))
            if wizard.quantity <= 0 or wizard.unit_price < 0:
                raise ValidationError(_('La cantidad debe ser positiva y el precio no puede ser negativo.'))

    def action_simulate(self):
        self.ensure_one()
        rows = self.env['dolan.discount.engine']._evaluate_lines(
            self.company_id, self.pos_config_id,
            [{'uuid': 'simulator', 'product': self.product_id, 'qty': self.quantity,
              'base_amount': self.quantity * self.unit_price}],
            payment_allocations=[], at=self.at,
        )
        details = [{
            'campaign': row['campaign_snapshot'].get('name'),
            'campaign_version': row['campaign_version'],
            'rule': row['rule_snapshot'].get('name'),
            'base': row['base_amount'],
            'discount': row['discount_amount'],
            'discount_percent': row['discount_amount'] * 100 / row['base_amount'] if row['base_amount'] else 0,
        } for row in rows]
        if self.payment_method_id:
            details.append({'notice': _('El medio seleccionado no se considera confirmado; las reglas de pago no califican en el simulador.')})
        self.result = json.dumps({
            'company': self.company_id.display_name, 'pos': self.pos_config_id.display_name,
            'at_server_context': fields.Datetime.to_string(self.at), 'product': self.product_id.display_name,
            'quantity': self.quantity, 'unit_price': self.unit_price,
            'discount_total': sum(row['discount_amount'] for row in rows), 'rules': details,
        }, ensure_ascii=False, indent=2)
        return {
            'type': 'ir.actions.act_window', 'name': _('Simulación de promociones'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
            'views': [(self.env.ref('DOLAN_discount_engine.view_dolan_discount_simulator_form').id, 'form')],
            'target': 'new',
        }
