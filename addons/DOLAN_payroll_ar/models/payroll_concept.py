# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

CONCEPT_KINDS = [
    ('rem', 'Remunerativo'),
    ('norem', 'No remunerativo'),
    ('ded', 'Descuento'),
    ('contrib', 'Contribución patronal'),
    ('info', 'Informativo'),
]

SICOSS_BUCKETS = [
    ('none', 'No informa'),
    ('sueldo', 'Sueldo + adicionales'),
    ('sac', 'SAC'),
    ('extra', 'Horas extras'),
    ('vac', 'Vacaciones'),
    ('adic', 'Adicionales'),
    ('premios', 'Premios'),
    ('norem', 'Conceptos no remunerativos'),
]


class DolanPayrollConcept(models.Model):
    """Concepto de liquidación con fórmula.

    ``formula`` es una expresión Python evaluada con ``safe_eval``. Variables
    disponibles: ``basic``, ``years``, ``worked_days``, ``hour_value``,
    ``inputs`` (dict código -> importe/cantidad), ``rules`` (dict código ->
    importe ya calculado en el recibo), ``REM``, ``NOREM``, ``DED``,
    ``agreement``, ``employee``, ``slip``, ``param(code)`` y los ayudantes
    ``ganancias()``, ``sac_amount()``, ``vacation_amount()``,
    ``vacation_discount()``, ``severance()``, ``notice()``,
    ``month_integration()``, ``unused_vacation()``, ``proportional_sac()``.
    """
    _name = 'dolan.payroll.concept'
    _description = 'Concepto de liquidación'
    _order = 'sequence, code'

    name = fields.Char('Concepto', required=True)
    code = fields.Char('Código', required=True, index=True)
    sequence = fields.Integer('Orden de cálculo', default=100)
    active = fields.Boolean(default=True)
    kind = fields.Selection(CONCEPT_KINDS, string='Tipo', required=True, default='rem')
    formula = fields.Text('Fórmula del importe', required=True, default='0.0')
    quantity_formula = fields.Char('Fórmula de cantidad',
                                   help='Opcional. Se imprime en el recibo (días, horas, %).')
    condition = fields.Char('Condición', help='Expresión opcional; si es falsa el concepto no se liquida.')
    in_monthly = fields.Boolean('Mensual', default=True)
    in_sac = fields.Boolean('SAC')
    in_final = fields.Boolean('Liquidación final')
    sac_base = fields.Boolean('Integra base de SAC',
                              help='Se suma para calcular la mejor remuneración del semestre.')
    gan_deductible = fields.Boolean('Deducible en Ganancias',
                                    help='Aportes que se restan de la ganancia bruta (jubilación, obra social, sindicato).')
    gan_withholding = fields.Boolean('Es retención de Ganancias')
    afip_code = fields.Char('Código ARCA (LSD)', help='Código de concepto declarado en el Libro de Sueldos Digital.')
    sicoss_bucket = fields.Selection(SICOSS_BUCKETS, string='Destino F.931', default='none', required=True)
    agreement_ids = fields.Many2many('dolan.payroll.agreement', string='Sólo para convenios',
                                     help='Vacío: aplica a todos.')
    account_id = fields.Many2one('account.account', string='Cuenta contable',
                                 help='Opcional: reemplaza la cuenta por defecto de la compañía.')
    note = fields.Text('Notas')

    _dolan_payroll_concept_code_uniq = models.Constraint(
        'UNIQUE(code)', 'El código de concepto debe ser único.'
    )

    @api.constrains('formula', 'condition', 'quantity_formula')
    def _check_syntax(self):
        for concept in self:
            for expr in (concept.formula, concept.condition, concept.quantity_formula):
                if not expr:
                    continue
                try:
                    compile(expr.strip(), '<concept %s>' % concept.code, 'eval')
                except SyntaxError as exc:
                    raise ValidationError(_('Fórmula inválida en %(code)s: %(err)s',
                                            code=concept.code, err=exc)) from exc

    def _applies_to(self, run_kind, agreement):
        self.ensure_one()
        if self.agreement_ids and agreement not in self.agreement_ids:
            return False
        return {
            'monthly': self.in_monthly,
            'sac': self.in_sac,
            'final': self.in_final,
        }.get(run_kind, False)

    def _evaluate(self, localdict):
        self.ensure_one()
        if self.condition and not safe_eval(self.condition.strip(), localdict):
            return None, None
        amount = safe_eval(self.formula.strip(), localdict) or 0.0
        quantity = safe_eval(self.quantity_formula.strip(), localdict) if self.quantity_formula else 0.0
        return float(amount), float(quantity or 0.0)
