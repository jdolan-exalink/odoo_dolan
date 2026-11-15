from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DolanBranch(models.Model):
    _name = 'dolan.branch'
    _description = 'Sucursal'
    _inherit = ['mail.thread']
    _order = 'company_id, sequence, name'

    name = fields.Char('Sucursal', required=True, tracking=True)
    code = fields.Char('Código', required=True, size=10, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True)
    partner_id = fields.Many2one('res.partner', 'Dirección', help='Domicilio de la sucursal (el que se informa en los comprobantes).')
    manager_id = fields.Many2one('res.users', 'Responsable', domain=[('share', '=', False)])
    warehouse_id = fields.Many2one('stock.warehouse', 'Depósito', domain="[('company_id', '=', company_id)]")
    journal_ids = fields.One2many('account.journal', 'dolan_branch_id', 'Diarios',
                                  help='Diarios de venta (punto de venta fiscal), caja y banco de la sucursal.')
    pricelist_id = fields.Many2one('product.pricelist', 'Lista de precios', domain="[('company_id', 'in', (company_id, False))]")
    user_ids = fields.Many2many('res.users', 'dolan_branch_res_users_rel', 'branch_id', 'user_id', 'Usuarios habilitados',
                                domain=[('share', '=', False)])
    move_count = fields.Integer('Comprobantes', compute='_compute_counts')

    _code_company_unique = models.Constraint('UNIQUE(company_id, code)', 'Ya hay una sucursal con ese código en la empresa.')
    _warehouse_unique = models.Constraint('UNIQUE(warehouse_id)', 'El depósito ya está asignado a otra sucursal.')

    @api.constrains('warehouse_id', 'company_id')
    def _check_warehouse_company(self):
        for branch in self:
            if branch.warehouse_id and branch.warehouse_id.company_id != branch.company_id:
                raise ValidationError(_('El depósito tiene que ser de la misma empresa que la sucursal.'))

    def _compute_counts(self):
        counts = dict(self.env['account.move']._read_group([('dolan_branch_id', 'in', self.ids)], ['dolan_branch_id'], ['__count']))
        for branch in self:
            branch.move_count = counts.get(branch, 0)

    def action_open_moves(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Comprobantes de %s') % self.name, 'res_model': 'account.move',
                'view_mode': 'list,form', 'domain': [('dolan_branch_id', '=', self.id)]}


class ResUsers(models.Model):
    _inherit = 'res.users'

    dolan_branch_ids = fields.Many2many('dolan.branch', 'dolan_branch_res_users_rel', 'user_id', 'branch_id', 'Sucursales')
    dolan_branch_id = fields.Many2one('dolan.branch', 'Sucursal por defecto',
                                      domain="[('id', 'in', dolan_branch_ids)]")

    @api.constrains('dolan_branch_id', 'dolan_branch_ids')
    def _check_default_branch(self):
        for user in self:
            if user.dolan_branch_id and user.dolan_branch_id not in user.dolan_branch_ids:
                raise ValidationError(_('La sucursal por defecto tiene que estar entre las habilitadas.'))

    def _dolan_current_branch(self, company):
        self.ensure_one()
        branch = self.dolan_branch_id
        if branch and branch.company_id == company:
            return branch
        return self.dolan_branch_ids.filtered(lambda b: b.company_id == company)[:1]


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    dolan_branch_id = fields.Many2one('dolan.branch', 'Sucursal', index=True,
                                      domain="[('company_id', '=', company_id)]")

    @api.constrains('dolan_branch_id', 'company_id')
    def _check_branch_company(self):
        for journal in self:
            if journal.dolan_branch_id and journal.dolan_branch_id.company_id != journal.company_id:
                raise ValidationError(_('La sucursal del diario tiene que ser de la misma empresa.'))


class AccountMove(models.Model):
    _inherit = 'account.move'

    dolan_branch_id = fields.Many2one('dolan.branch', 'Sucursal', compute='_compute_dolan_branch', store=True,
                                      readonly=False, index=True, precompute=True,
                                      domain="[('company_id', '=', company_id)]")

    @api.depends('journal_id')
    def _compute_dolan_branch(self):
        for move in self:
            if move.journal_id.dolan_branch_id:
                move.dolan_branch_id = move.journal_id.dolan_branch_id
            elif not move.dolan_branch_id:
                move.dolan_branch_id = self.env.user._dolan_current_branch(move.company_id or self.env.company)


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    dolan_branch_ids = fields.One2many('dolan.branch', 'warehouse_id')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dolan_branch_id = fields.Many2one('dolan.branch', 'Sucursal', compute='_compute_dolan_branch', store=True, index=True)

    @api.depends('picking_type_id.warehouse_id')
    def _compute_dolan_branch(self):
        for picking in self:
            picking.dolan_branch_id = picking.picking_type_id.warehouse_id.dolan_branch_ids[:1]
