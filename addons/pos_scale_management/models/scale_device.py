from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.catalog_resolver import CatalogResolver
from ..services.price_resolver import PriceResolver
from ..services.export_validator import ExportValidator


class ScaleDevice(models.Model):
    _name = 'scale.device'
    _description = 'Balanza comercial'
    _order = 'warehouse_id, name'
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True, index=True, string='Sucursal')
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Lista base de precios de la sucursal',
        check_company=True,
        help='Usá la misma lista para todas las balanzas de la sucursal. Si está vacía, se utiliza el precio estándar del producto.',
    )
    location = fields.Char()
    brand = fields.Selection([('kretz', 'Kretz'), ('other', 'Otra marca')], required=True, default='kretz')
    model_name = fields.Char(string='Modelo')
    serial_number = fields.Char(string='Identificador / serie')
    profile_id = fields.Many2one('scale.export.profile', required=True, check_company=False, ondelete='restrict')
    barcode_profile_id = fields.Many2one('scale.barcode.profile', ondelete='restrict')
    active = fields.Boolean(default=True)
    product_assignment_ids = fields.One2many('scale.product.assignment', 'device_id', string='Productos y categorías')
    price_override_ids = fields.One2many('scale.price.override', 'device_id', string='Excepciones de precio')
    export_job_ids = fields.One2many('scale.export.job', 'device_id', string='Historial')
    product_count = fields.Integer(compute='_compute_product_count')
    last_export_at = fields.Datetime(compute='_compute_last_export', store=True)
    last_export_state = fields.Selection(related='last_export_id.state', string='Última exportación')
    last_export_id = fields.Many2one('scale.export.job', compute='_compute_last_export', store=True)

    _scale_device_code_company_uniq = models.Constraint(
        'UNIQUE(company_id, code)',
        'El código de balanza debe ser único dentro de la empresa.',
    )

    @api.constrains('warehouse_id', 'company_id', 'brand', 'profile_id')
    def _check_configuration(self):
        for device in self:
            if device.warehouse_id.company_id != device.company_id:
                raise ValidationError(_('La sucursal debe pertenecer a la misma empresa que la balanza.'))
            if device.profile_id.brand != device.brand:
                raise ValidationError(_('La marca del perfil de exportación no coincide con la balanza.'))
            if device.pricelist_id and device.pricelist_id.company_id and device.pricelist_id.company_id != device.company_id:
                raise ValidationError(_('La lista de precios pertenece a otra empresa.'))

    @api.depends('product_assignment_ids', 'product_assignment_ids.active', 'product_assignment_ids.disposition')
    def _compute_product_count(self):
        for device in self:
            device.product_count = len(CatalogResolver(device).resolve())

    @api.depends('export_job_ids.create_date', 'export_job_ids.state')
    def _compute_last_export(self):
        for device in self:
            last_job = self.env['scale.export.job'].search([('device_id', '=', device.id)], order='create_date desc, id desc', limit=1)
            device.last_export_id = last_job
            device.last_export_at = last_job.create_date if last_job else False

    def _resolve_export_preview(self):
        self.ensure_one()
        products = CatalogResolver(self).resolve()
        prices = PriceResolver(self).resolve(products)
        return products, prices, ExportValidator(self).validate(products, prices)

    def action_preview_export(self):
        self.ensure_one()
        if not any(self.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
            'pos_scale_management.group_scale_operator',
        )):
            raise AccessError(_('No tenés permiso para previsualizar exportaciones de balanzas.'))
        job = self.env['scale.export.job'].create_preview(self)
        return {
            'type': 'ir.actions.act_window', 'res_model': 'scale.export.job',
            'res_id': job.id, 'view_mode': 'form', 'target': 'current',
        }

    def action_generate_export(self):
        self.ensure_one()
        if not any(self.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
        )):
            raise AccessError(_('Solo un administrador o responsable de sucursal puede solicitar una exportación.'))
        job = self.env['scale.export.job'].create_export(self)
        return {
            'type': 'ir.actions.act_window', 'res_model': 'scale.export.job',
            'res_id': job.id, 'view_mode': 'form', 'target': 'current',
        }
