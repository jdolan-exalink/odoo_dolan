# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


class DolanPayrollAgreement(models.Model):
    _name = 'dolan.payroll.agreement'
    _description = 'Convenio colectivo de trabajo'
    _order = 'sequence, name'

    name = fields.Char('Convenio', required=True)
    code = fields.Char('Código CCT', help='Ej.: 130/75 (Comercio), 260/75 (UOM).')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_agreement = fields.Boolean('Trabajador convencionado', default=True,
                                  help='Desmarcar para personal fuera de convenio (marca SICOSS).')
    union_partner_id = fields.Many2one('res.partner', string='Sindicato')
    union_rate = fields.Float('Aporte sindical %', help='Sólo se descuenta a afiliados.')
    solidarity_rate = fields.Float('Aporte solidario / asistencial %',
                                   help='Se descuenta a todos los trabajadores del convenio.')
    employer_fund_rate = fields.Float('Contribución patronal del convenio %',
                                      help='Ej.: FAECYS 0,5 % en Comercio.')
    seniority_rate = fields.Float('Antigüedad % por año', help='Sobre el básico. Comercio: 1 %.')
    attendance_rate = fields.Float('Presentismo %', help='Sobre básico + antigüedad. Comercio: 8,33 %.')
    monthly_hours = fields.Float('Divisor horario mensual', default=200.0,
                                 help='Horas por mes para valuar la hora (Comercio: 200).')
    category_ids = fields.One2many('dolan.payroll.agreement.category', 'agreement_id', string='Categorías')
    note = fields.Text('Notas')


class DolanPayrollAgreementCategory(models.Model):
    _name = 'dolan.payroll.agreement.category'
    _description = 'Categoría de convenio'
    _order = 'agreement_id, sequence, name'

    agreement_id = fields.Many2one('dolan.payroll.agreement', required=True, ondelete='cascade')
    name = fields.Char('Categoría', required=True)
    code = fields.Char('Código')
    sequence = fields.Integer(default=10)
    scale_ids = fields.One2many('dolan.payroll.agreement.scale', 'category_id', string='Escala salarial')
    current_basic = fields.Float('Básico vigente', compute='_compute_current_basic')

    @api.depends('scale_ids.amount', 'scale_ids.date_from')
    def _compute_current_basic(self):
        today = fields.Date.context_today(self)
        for category in self:
            category.current_basic = category.get_basic(today)

    def get_basic(self, date):
        self.ensure_one()
        scales = self.scale_ids.filtered(lambda s: s.date_from <= date).sorted('date_from', reverse=True)
        return scales[:1].amount if scales else 0.0

    @api.depends('agreement_id.code', 'name')
    def _compute_display_name(self):
        for category in self:
            prefix = category.agreement_id.code or category.agreement_id.name or ''
            category.display_name = '%s - %s' % (prefix, category.name) if prefix else category.name


class DolanPayrollAgreementScale(models.Model):
    _name = 'dolan.payroll.agreement.scale'
    _description = 'Escala salarial de convenio'
    _order = 'date_from desc'

    category_id = fields.Many2one('dolan.payroll.agreement.category', required=True, ondelete='cascade')
    date_from = fields.Date('Vigente desde', required=True)
    amount = fields.Float('Básico mensual', required=True)
    note = fields.Char('Acuerdo / homologación')
