# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
"""Sueldos pasa a tener permisos propios (20.0.1.1.0).

Hasta 20.0.1.0.0 cualquier Oficial de Empleados veía sueldos y recibos y los
Administradores de Empleados configuraban convenios. Para que nadie pierda
acceso al actualizar, esos usuarios reciben los grupos nuevos equivalentes;
después RRHH puede quitárselos a quien no liquida sueldos.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    pairs = (
        ('hr.group_hr_manager', 'DOLAN_payroll_ar.group_dolan_payroll_manager'),
        ('hr.group_hr_user', 'DOLAN_payroll_ar.group_dolan_payroll_user'),
    )
    for source_xmlid, target_xmlid in pairs:
        source = env.ref(source_xmlid, raise_if_not_found=False)
        target = env.ref(target_xmlid, raise_if_not_found=False)
        if not source or not target:
            continue
        users = source.all_user_ids.filtered(lambda u: not u.share) - target.all_user_ids
        if users:
            target.write({'user_ids': [(4, user.id) for user in users]})
