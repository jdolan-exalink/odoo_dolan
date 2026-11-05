# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def validate_cbu_checksum(cbu_str):
    """Valida el dígito verificador de los 22 dígitos del CBU según la normativa oficial del BCRA.
    
    Bloque 1 (Entidad y Sucursal, 8 dígitos):
      Ponderadores: [7, 1, 3, 9, 7, 1, 3] sobre los primeros 7 dígitos.
      Dígito verificador: (10 - (suma % 10)) % 10 debe ser igual al 8vo dígito.
      
    Bloque 2 (Cuenta bancaria, 14 dígitos):
      Ponderadores: [3, 9, 7, 1, 3, 9, 7, 1, 3, 9, 7, 1, 3] sobre los 13 dígitos (posiciones 9 a 21).
      Dígito verificador: (10 - (suma % 10)) % 10 debe ser igual al dígito 22.
    """
    if not cbu_str:
        return False
    digits = ''.join(c for c in cbu_str if c.isdigit())
    if len(digits) != 22:
        return False

    # Bloque 1
    w1 = [7, 1, 3, 9, 7, 1, 3]
    s1 = sum(int(digits[i]) * w1[i] for i in range(7))
    d1 = (10 - (s1 % 10)) % 10
    if d1 != int(digits[7]):
        return False

    # Bloque 2
    w2 = [3, 9, 7, 1, 3, 9, 7, 1, 3, 9, 7, 1, 3]
    s2 = sum(int(digits[8 + i]) * w2[i] for i in range(13))
    d2 = (10 - (s2 % 10)) % 10
    if d2 != int(digits[21]):
        return False

    return True


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    cbu_alias = fields.Char(
        string='Alias CBU / CVU',
        help='Alias oficial de 6 a 20 caracteres alfanuméricos asignado por el banco o billetera.',
    )
    is_cbu = fields.Boolean(
        string='Es CBU / CVU Argentino',
        compute='_compute_is_cbu',
        store=True,
    )

    @api.depends('account_number', 'partner_id.country_id')
    def _compute_is_cbu(self):
        for rec in self:
            digits = ''.join(c for c in (rec.account_number or '') if c.isdigit())
            rec.is_cbu = len(digits) == 22 and (
                not rec.partner_id.country_id or rec.partner_id.country_id.code == 'AR'
            )

    @api.constrains('account_number')
    def _check_cbu_format(self):
        for rec in self:
            if not rec.account_number:
                continue
            digits = ''.join(c for c in rec.account_number if c.isdigit())
            # Si tiene 22 dígitos numéricos y el país es Argentina, se valida como CBU/CVU
            is_ar = not rec.partner_id.country_id or rec.partner_id.country_id.code == 'AR'
            if len(digits) == 22 and is_ar:
                if not validate_cbu_checksum(digits):
                    raise ValidationError(_(
                        'El CBU/CVU "%s" no es válido. Los dígitos verificadores no cumplen '
                        'con el algoritmo oficial del Banco Central de la República Argentina (BCRA).'
                    ) % rec.account_number)

    @api.constrains('cbu_alias')
    def _check_cbu_alias_format(self):
        for rec in self:
            if not rec.cbu_alias:
                continue
            alias = rec.cbu_alias.strip()
            if len(alias) < 6 or len(alias) > 20:
                raise ValidationError(_(
                    'El Alias CBU/CVU debe tener entre 6 y 20 caracteres.'
                ))
            if not re.match(r'^[a-zA-Z0-9.\-_]+$', alias):
                raise ValidationError(_(
                    'El Alias CBU/CVU sólo puede contener letras, números, puntos o guiones.'
                ))
