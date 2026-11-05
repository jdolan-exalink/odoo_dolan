# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DolanMrpWorkorderTime(models.Model):
    _name = 'dolan.mrp.workorder.time'
    _description = 'Registro de Tiempo y Costo Horario de Operario en Taller (Shop Floor)'
    _order = 'date_start desc, id desc'

    workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Orden de Trabajo',
        required=True,
        ondelete='cascade',
        index=True,
    )
    production_id = fields.Many2one(
        'mrp.production',
        related='workorder_id.production_id',
        string='Orden de Fabricación',
        store=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Operario de Planta',
        required=True,
    )
    date_start = fields.Datetime(
        string='Inicio',
        required=True,
        default=fields.Datetime.now,
    )
    date_end = fields.Datetime(string='Fin')
    duration_minutes = fields.Float(
        string='Duración (min)',
        compute='_compute_duration_and_cost',
        store=True,
    )
    hourly_cost = fields.Monetary(
        string='Costo Hora Operario',
        default=25.0,
        currency_field='currency_id',
    )
    labor_cost_total = fields.Monetary(
        string='Costo Mano de Obra',
        compute='_compute_duration_and_cost',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    notes = fields.Char(string='Observación de Turno')

    @api.depends('date_start', 'date_end', 'hourly_cost')
    def _compute_duration_and_cost(self):
        now = fields.Datetime.now()
        for rec in self:
            end_dt = rec.date_end or now
            if rec.date_start and end_dt >= rec.date_start:
                mins = (end_dt - rec.date_start).total_seconds() / 60.0
            else:
                mins = 0.0
            rec.duration_minutes = round(mins, 2)
            rec.labor_cost_total = round((mins / 60.0) * (rec.hourly_cost or 0.0), 2)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    shopfloor_employee_id = fields.Many2one(
        'hr.employee',
        string='Operario Asignado (Taller)',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo / Máquina Asociada',
    )
    shopfloor_time_ids = fields.One2many(
        'dolan.mrp.workorder.time',
        'workorder_id',
        string='Tiempos de Operario en Taller',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    total_labor_cost = fields.Monetary(
        string='Costo Total Mano de Obra RRHH',
        compute='_compute_total_labor_cost',
        currency_field='currency_id',
    )
    maintenance_request_count = fields.Integer(
        string='Solicitudes de Mantenimiento',
        compute='_compute_maintenance_request_count',
    )
    quality_check_ids = fields.One2many(
        'dolan.quality.check',
        'workorder_id',
        string='Controles de Calidad de la OT',
    )
    scrap_qty_recorded = fields.Float(
        string='Cantidad Desechada (Scrap)',
        default=0.0,
    )

    @api.depends('shopfloor_time_ids.labor_cost_total')
    def _compute_total_labor_cost(self):
        for wo in self:
            wo.total_labor_cost = sum(wo.shopfloor_time_ids.mapped('labor_cost_total'))

    def _compute_maintenance_request_count(self):
        Request = self.env['maintenance.request']
        for wo in self:
            if wo.equipment_id:
                wo.maintenance_request_count = Request.search_count(
                    [('equipment_id', '=', wo.equipment_id.id)]
                )
            else:
                wo.maintenance_request_count = 0

    def action_shopfloor_start(self):
        """Start workorder from Shop Floor terminal and open operator time log."""
        now = fields.Datetime.now()
        for wo in self:
            if hasattr(wo, 'button_start'):
                wo.button_start()
            else:
                wo.state = 'progress'
            employee = wo.shopfloor_employee_id or self.env['hr.employee'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
            if not employee:
                employee = self.env['hr.employee'].search([], limit=1)
            if employee:
                wo.shopfloor_employee_id = employee.id
                hourly_rate = getattr(employee, 'hourly_cost', 25.0) or 25.0
                self.env['dolan.mrp.workorder.time'].create({
                    'workorder_id': wo.id,
                    'employee_id': employee.id,
                    'date_start': now,
                    'hourly_cost': hourly_rate,
                })
        return True

    def action_shopfloor_pause(self):
        """Pause workorder and close active operator time logs."""
        now = fields.Datetime.now()
        for wo in self:
            if hasattr(wo, 'button_pending'):
                wo.button_pending()
            open_logs = wo.shopfloor_time_ids.filtered(lambda t: not t.date_end)
            open_logs.write({'date_end': now})
        return True

    def action_shopfloor_done(self):
        """Verify mandatory quality checks, close operator timer and finish workorder."""
        now = fields.Datetime.now()
        for wo in self:
            pending_checks = wo.quality_check_ids.filtered(lambda c: c.quality_state == 'none')
            if pending_checks:
                raise UserError(
                    _('Debe completar los Controles de Calidad pendientes antes de terminar la Orden de Trabajo.')
                )
            open_logs = wo.shopfloor_time_ids.filtered(lambda t: not t.date_end)
            open_logs.write({'date_end': now})
            if hasattr(wo, 'button_finish'):
                wo.button_finish()
            else:
                wo.state = 'done'
        return True

    def action_shopfloor_register_scrap(self):
        """Register 1 unit of production scrap directly from Shop Floor."""
        self.ensure_one()
        if not self.production_id:
            raise UserError(_('La Orden de Trabajo no tiene una Orden de Fabricación asociada.'))
        scrap = self.env['stock.scrap'].create({
            'product_id': self.product_id.id,
            'scrap_qty': 1.0,
            'product_uom_id': self.product_id.uom_id.id,
            'production_id': self.production_id.id,
            'workorder_id': self.id,
        })
        self.scrap_qty_recorded += 1.0
        return {
            'type': 'ir.actions.act_window',
            'name': _('Desecho de Producción (Scrap)'),
            'res_model': 'stock.scrap',
            'res_id': scrap.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_shopfloor_maintenance_request(self):
        """Create an equipment maintenance request directly from the Shop Floor terminal."""
        self.ensure_one()
        request_rec = self.env['maintenance.request'].create({
            'name': _('Parada / Avería en Taller: %s (%s)') % (self.name, self.workcenter_id.display_name),
            'equipment_id': self.equipment_id.id if self.equipment_id else False,
            'employee_id': self.shopfloor_employee_id.id if self.shopfloor_employee_id else False,
            'description': _(
                'Solicitud generada desde Terminal de Taller (Shop Floor).\n'
                'Orden de Fabricación: %s\nCentro de Trabajo: %s'
            ) % (self.production_id.display_name or '-', self.workcenter_id.display_name or '-'),
            'maintenance_type': 'corrective',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Mantenimiento de Equipo'),
            'res_model': 'maintenance.request',
            'res_id': request_rec.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_maintenance_request(self):
        return self.action_shopfloor_maintenance_request()
