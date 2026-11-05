# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DolanQualityPoint(models.Model):
    _name = 'dolan.quality.point'
    _description = 'Punto de Control de Calidad (Quality Point)'
    _order = 'sequence asc, id desc'

    name = fields.Char(
        string='Código de Punto de Control',
        required=True,
        default=lambda self: _('Nuevo QCP'),
        copy=False,
    )
    title = fields.Char(string='Título del Control', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    product_ids = fields.Many2many(
        'product.product',
        string='Productos Controlados',
        help='Si se deja vacío, aplica a todos los productos de los tipos de operación seleccionados.',
    )
    picking_type_ids = fields.Many2many(
        'stock.picking.type',
        string='Tipos de Operación (Recepciones / MRP / Entregas)',
        required=True,
    )
    test_type = fields.Selection(
        selection=[
            ('pass_fail', 'Aprobado / Rechazado (Pass - Fail)'),
            ('measure', 'Medición con Tolerancia (Min / Max)'),
            ('instructions', 'Instrucción de Trabajo / Verificación Visual'),
        ],
        string='Tipo de Control',
        default='pass_fail',
        required=True,
    )
    norm = fields.Float(string='Valor Nominal', default=10.0)
    tolerance_min = fields.Float(string='Tolerancia Mínima', default=9.5)
    tolerance_max = fields.Float(string='Tolerancia Máxima', default=10.5)
    norm_unit = fields.Char(string='Unidad de Medida (ej. mm, kg, °C)', default='mm')
    user_id = fields.Many2one(
        'res.users',
        string='Responsable de Calidad',
        default=lambda self: self.env.user,
    )
    instructions = fields.Html(string='Instrucciones de Inspección')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo QCP')) == _('Nuevo QCP'):
                vals['name'] = f"QCP-{fields.Datetime.now().strftime('%m%d%H%M%S')}"
        return super().create(vals_list)


class DolanQualityCheck(models.Model):
    _name = 'dolan.quality.check'
    _description = 'Control de Calidad en Recepciones y Producción (Quality Check)'
    _order = 'id desc'

    name = fields.Char(
        string='Referencia de Control',
        required=True,
        default=lambda self: _('Nuevo Control'),
        copy=False,
    )
    point_id = fields.Many2one(
        'dolan.quality.point',
        string='Punto de Control',
    )
    title = fields.Char(
        string='Criterio a Verificar',
        required=True,
        default=lambda self: _('Inspección de Calidad'),
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto Inspeccionado',
        required=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote / Número de Serie',
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Recepción / Remito',
        ondelete='cascade',
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Fabricación',
        ondelete='cascade',
    )
    workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Orden de Trabajo (Taller)',
        ondelete='cascade',
    )
    test_type = fields.Selection(
        selection=[
            ('pass_fail', 'Aprobado / Rechazado (Pass - Fail)'),
            ('measure', 'Medición con Tolerancia (Min / Max)'),
            ('instructions', 'Instrucción de Trabajo / Verificación Visual'),
        ],
        string='Tipo de Control',
        default='pass_fail',
        required=True,
    )
    measure = fields.Float(string='Valor Medido')
    tolerance_min = fields.Float(string='Tolerancia Mínima', default=0.0)
    tolerance_max = fields.Float(string='Tolerancia Máxima', default=100.0)
    norm_unit = fields.Char(string='Unidad', default='mm')
    quality_state = fields.Selection(
        selection=[
            ('none', 'Por Realizar'),
            ('pass', 'Aprobado'),
            ('fail', 'Rechazado'),
        ],
        string='Resultado de Calidad',
        default='none',
        required=True,
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Inspector',
        default=lambda self: self.env.user,
    )
    checked_date = fields.Datetime(string='Fecha de Inspección')
    instructions = fields.Html(string='Instrucciones')
    notes = fields.Text(string='Observaciones del Inspector')
    alert_ids = fields.One2many(
        'dolan.quality.alert',
        'check_id',
        string='Alertas de No Conformidad',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo Control')) == _('Nuevo Control'):
                vals['name'] = f"QC-{fields.Datetime.now().strftime('%m%d%H%M%S')}"
        return super().create(vals_list)

    def action_pass(self):
        for check in self:
            check.write({
                'quality_state': 'pass',
                'checked_date': fields.Datetime.now(),
                'user_id': self.env.uid,
            })
        return True

    def action_fail(self):
        for check in self:
            check.write({
                'quality_state': 'fail',
                'checked_date': fields.Datetime.now(),
                'user_id': self.env.uid,
            })
        return True

    def action_evaluate_measure(self):
        """Evaluate dimensional measurement against [tolerance_min, tolerance_max]."""
        for check in self:
            if check.tolerance_min <= check.measure <= check.tolerance_max:
                check.action_pass()
            else:
                check.action_fail()
        return True

    def action_create_quality_alert(self):
        self.ensure_one()
        alert = self.env['dolan.quality.alert'].create({
            'title': _('No Conformidad en %s (%s)') % (self.product_id.display_name, self.name),
            'check_id': self.id,
            'product_id': self.product_id.id,
            'lot_id': self.lot_id.id if self.lot_id else False,
            'picking_id': self.picking_id.id if self.picking_id else False,
            'production_id': self.production_id.id if self.production_id else False,
            'user_id': self.env.uid,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alerta de Calidad / No Conformidad'),
            'res_model': 'dolan.quality.alert',
            'res_id': alert.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DolanQualityAlert(models.Model):
    _name = 'dolan.quality.alert'
    _description = 'Alerta de Calidad y No Conformidad (CAPA)'
    _order = 'priority desc, id desc'

    name = fields.Char(
        string='Código de Alerta',
        required=True,
        default=lambda self: _('Nueva Alerta'),
        copy=False,
    )
    title = fields.Char(string='Motivo de No Conformidad', required=True)
    check_id = fields.Many2one('dolan.quality.check', string='Control de Origen')
    product_id = fields.Many2one('product.product', string='Producto Afectado', required=True)
    lot_id = fields.Many2one('stock.lot', string='Lote / Serie')
    partner_id = fields.Many2one('res.partner', string='Proveedor / Cliente')
    picking_id = fields.Many2one('stock.picking', string='Remito Asociado')
    production_id = fields.Many2one('mrp.production', string='Orden de Fabricación')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Centro de Trabajo')
    user_id = fields.Many2one(
        'res.users',
        string='Responsable de Calidad',
        default=lambda self: self.env.user,
    )
    priority = fields.Selection(
        selection=[('0', 'Baja'), ('1', 'Media'), ('2', 'Alta'), ('3', 'Crítica / Bloqueante')],
        string='Severidad',
        default='2',
    )
    stage = fields.Selection(
        selection=[
            ('new', 'Detectada'),
            ('root_cause', 'Análisis Causa Raíz'),
            ('action_plan', 'Acción Correctiva en Curso'),
            ('resolved', 'Verificada y Cerrada'),
        ],
        string='Etapa CAPA',
        default='new',
        required=True,
        index=True,
    )
    description = fields.Text(string='Descripción del Defecto')
    root_cause = fields.Text(string='Análisis de Causa Raíz (5 Porqués / Ishikawa)')
    corrective_action = fields.Text(string='Acción Correctiva (CAPA)')
    preventive_action = fields.Text(string='Acción Preventiva')
    date_assign = fields.Datetime(string='Fecha de Detección', default=fields.Datetime.now)
    date_close = fields.Datetime(string='Fecha de Cierre')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva Alerta')) == _('Nueva Alerta'):
                vals['name'] = f"QA-{fields.Datetime.now().strftime('%m%d%H%M%S')}"
        return super().create(vals_list)

    def action_start_root_cause(self):
        self.write({'stage': 'root_cause'})

    def action_start_corrective_plan(self):
        self.write({'stage': 'action_plan'})

    def action_mark_resolved(self):
        self.write({'stage': 'resolved', 'date_close': fields.Datetime.now()})


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dolan_quality_check_ids = fields.One2many(
        'dolan.quality.check',
        'picking_id',
        string='Controles de Calidad',
    )
    dolan_quality_check_todo_count = fields.Integer(
        string='Controles Pendientes',
        compute='_compute_dolan_quality_check_counts',
    )

    def _compute_dolan_quality_check_counts(self):
        for picking in self:
            picking.dolan_quality_check_todo_count = len(
                picking.dolan_quality_check_ids.filtered(lambda c: c.quality_state == 'none')
            )

    def action_generate_quality_checks(self):
        """Generate Quality Checks matching this picking's operation type and products."""
        Point = self.env['dolan.quality.point']
        Check = self.env['dolan.quality.check']
        for picking in self:
            points = Point.search([('picking_type_ids', 'in', picking.picking_type_id.id)])
            for point in points:
                for move in picking.move_ids:
                    if point.product_ids and move.product_id not in point.product_ids:
                        continue
                    already = picking.dolan_quality_check_ids.filtered(
                        lambda c: c.point_id == point and c.product_id == move.product_id
                    )
                    if not already:
                        Check.create({
                            'point_id': point.id,
                            'title': point.title,
                            'product_id': move.product_id.id,
                            'picking_id': picking.id,
                            'test_type': point.test_type,
                            'tolerance_min': point.tolerance_min,
                            'tolerance_max': point.tolerance_max,
                            'norm_unit': point.norm_unit,
                            'instructions': point.instructions,
                        })
        return True


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    dolan_quality_check_ids = fields.One2many(
        'dolan.quality.check',
        'production_id',
        string='Controles de Calidad de Fabricación',
    )
