# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import math
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplateRental(models.Model):
    _inherit = 'product.template'

    is_rental = fields.Boolean(
        string='Puede ser Alquilado',
        default=False,
        help='Permite seleccionar este producto en órdenes de alquiler.',
    )
    rental_price_hour = fields.Float(
        string='Tarifa por Hora',
        digits='Product Price',
        default=0.0,
    )
    rental_price_day = fields.Float(
        string='Tarifa por Día',
        digits='Product Price',
        default=0.0,
    )
    rental_price_week = fields.Float(
        string='Tarifa por Semana (7 días)',
        digits='Product Price',
        default=0.0,
    )
    rental_price_month = fields.Float(
        string='Tarifa por Mes (30 días)',
        digits='Product Price',
        default=0.0,
    )
    extra_hour_penalty = fields.Float(
        string='Penalidad por Hora Extra',
        digits='Product Price',
        default=0.0,
        help='Recargo aplicado por cada hora de retraso en la devolución.',
    )
    extra_day_penalty = fields.Float(
        string='Penalidad por Día Extra',
        digits='Product Price',
        default=0.0,
        help='Recargo aplicado por cada día adicional de retraso en la devolución.',
    )
    rental_security_deposit = fields.Float(
        string='Depósito en Garantía Sugerido',
        digits='Product Price',
        default=0.0,
    )

    @api.constrains(
        'rental_price_hour',
        'rental_price_day',
        'rental_price_week',
        'rental_price_month',
        'extra_hour_penalty',
        'extra_day_penalty',
    )
    def _check_rental_prices_positive(self):
        for tmpl in self:
            if any(
                val < 0
                for val in (
                    tmpl.rental_price_hour,
                    tmpl.rental_price_day,
                    tmpl.rental_price_week,
                    tmpl.rental_price_month,
                    tmpl.extra_hour_penalty,
                    tmpl.extra_day_penalty,
                )
            ):
                raise ValidationError(_('Las tarifas y penalidades de alquiler no pueden ser negativas.'))

    def compute_optimal_rental_price(self, duration_hours):
        """Calcula el precio unitario óptimo para la duración en horas dada."""
        self.ensure_one()
        if duration_hours <= 0:
            return self.rental_price_day or self.list_price or 0.0

        duration_days = math.ceil(duration_hours / 24.0)
        if duration_hours < 24.0 and self.rental_price_hour > 0:
            hourly_total = math.ceil(duration_hours) * self.rental_price_hour
            if self.rental_price_day > 0:
                return min(hourly_total, self.rental_price_day)
            return hourly_total

        if duration_days >= 30 and self.rental_price_month > 0:
            months = duration_days // 30
            rem_days = duration_days % 30
            daily_rate = self.rental_price_day or (self.rental_price_month / 30.0)
            return (months * self.rental_price_month) + (rem_days * daily_rate)

        if duration_days >= 7 and self.rental_price_week > 0:
            weeks = duration_days // 7
            rem_days = duration_days % 7
            daily_rate = self.rental_price_day or (self.rental_price_week / 7.0)
            return (weeks * self.rental_price_week) + (rem_days * daily_rate)

        if self.rental_price_day > 0:
            return duration_days * self.rental_price_day

        if self.rental_price_hour > 0:
            return math.ceil(duration_hours) * self.rental_price_hour

        return duration_days * (self.list_price or 0.0)


class ProductProductRental(models.Model):
    _inherit = 'product.product'

    def compute_optimal_rental_price(self, duration_hours):
        self.ensure_one()
        return self.product_tmpl_id.compute_optimal_rental_price(duration_hours)
