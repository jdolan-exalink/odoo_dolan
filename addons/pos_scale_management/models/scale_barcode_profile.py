import re

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ScaleBarcodeProfile(models.Model):
    _name = 'scale.barcode.profile'
    _description = 'Perfil de código de etiqueta de balanza'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    barcode_length = fields.Integer(required=True, default=13)
    prefix = fields.Char(help='Prefijo literal observado en una etiqueta real; no se asume uno por defecto.')
    product_start = fields.Integer(string='Posición inicial del código de producto', default=2, required=True)
    product_length = fields.Integer(string='Longitud del código de producto', default=5, required=True)
    value_start = fields.Integer(string='Posición inicial del valor variable', default=7, required=True)
    value_length = fields.Integer(string='Longitud del valor variable', default=5, required=True)
    value_type = fields.Selection([('weight', 'Peso'), ('amount', 'Importe')], required=True, default='weight')
    decimals = fields.Integer(default=3, required=True)
    check_digit = fields.Boolean(string='Validar dígito de control EAN-13')
    active = fields.Boolean(default=True)

    _scale_barcode_profile_code_uniq = models.Constraint(
        'UNIQUE(code)',
        'El código del perfil de etiqueta debe ser único.',
    )
    _scale_barcode_profile_lengths_check = models.Constraint(
        'CHECK(barcode_length > 0 AND product_length > 0 AND value_length > 0 AND decimals >= 0 AND product_start > 0 AND value_start > 0)',
        'Las longitudes, posiciones y precisión deben ser válidas.',
    )

    def interpret(self, barcode):
        self.ensure_one()
        code = (barcode or '').strip()
        if len(code) != self.barcode_length or not code.isdigit():
            raise ValidationError(_('El código debe contener exactamente %s dígitos.') % self.barcode_length)
        if self.prefix and not code.startswith(self.prefix):
            raise ValidationError(_('El código no coincide con el prefijo configurado.'))
        if self.check_digit and (len(code) != 13 or self._ean13_check_digit(code[:-1]) != code[-1]):
            raise ValidationError(_('El dígito de control EAN-13 no es válido.'))
        if self.prefix and len(self.prefix) >= self.product_start:
            raise ValidationError(_('El prefijo configurado invade el segmento del producto.'))
        product_slice = code[self.product_start - 1:self.product_start - 1 + self.product_length]
        value_slice = code[self.value_start - 1:self.value_start - 1 + self.value_length]
        if len(product_slice) != self.product_length or len(value_slice) != self.value_length:
            raise ValidationError(_('Las posiciones configuradas exceden el largo del código.'))
        return {
            'product_code': product_slice,
            'value_type': self.value_type,
            'value': int(value_slice) / (10 ** self.decimals),
        }

    @staticmethod
    def _ean13_check_digit(first_twelve):
        if len(first_twelve) != 12 or not first_twelve.isdigit():
            return ''
        total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(first_twelve))
        return str((10 - total % 10) % 10)
