# -*- coding: utf-8 -*-
"""Vistas genéricas Gantt, Mapa, Grilla y Cohorte.

Los cuatro tipos de vista (``dolan_gantt``, ``dolan_map``, ``dolan_grid`` y
``dolan_cohort``) sirven para cualquier modelo: alcanza con una vista cuyo
arch tenga esa etiqueta y sus atributos. Además, este módulo agrega vistas
listas para usar a las acciones de Proyecto, Partes de horas, Fabricación,
Flota, Alquileres, Suscripciones, Contactos, CRM y Ventas cuando esas apps
están instaladas. El registro se repite al cargar el servidor porque la
actualización de una app pisa el ``view_mode`` de sus acciones.
"""
import logging

from lxml import etree

from odoo import api, models, _

_logger = logging.getLogger(__name__)

GENERIC_TYPES = ('dolan_gantt', 'dolan_map', 'dolan_grid', 'dolan_cohort')

VALID_ATTRIBUTES = {
    'dolan_gantt': {'string', 'date_start', 'date_stop', 'date_start_fallback', 'default_group_by',
                    'default_scale', 'progress', 'color', 'create', 'edit'},
    'dolan_map': {'string', 'res_partner', 'title'},
    'dolan_grid': {'string', 'row_field', 'date_field', 'measure', 'range', 'editable'},
    'dolan_cohort': {'string', 'date_start', 'date_stop', 'interval', 'measure', 'periods'},
}
REQUIRED_ATTRIBUTES = {
    'dolan_gantt': ('date_start',),
    'dolan_map': (),
    'dolan_grid': ('row_field', 'date_field', 'measure'),
    'dolan_cohort': ('date_start',),
}
FIELD_ATTRIBUTES = {'date_start', 'date_stop', 'date_start_fallback', 'default_group_by', 'progress',
                    'color', 'res_partner', 'row_field', 'date_field', 'measure'}

# (modelo, acción, tipo, atributos)
DEFAULT_REGISTRATIONS = [
    ('project.task', 'project.action_view_all_task', 'dolan_gantt',
     {'string': 'Planificación', 'date_start': 'date_assign', 'date_start_fallback': 'create_date',
      'date_stop': 'date_deadline', 'default_group_by': 'project_id'}),
    ('project.task', 'project.action_view_all_task', 'dolan_map',
     {'string': 'Mapa', 'res_partner': 'partner_id'}),
    ('project.task', 'project.action_view_all_task', 'dolan_cohort',
     {'string': 'Cohorte', 'date_start': 'create_date', 'date_stop': 'date_end', 'interval': 'month'}),
    ('account.analytic.line', 'hr_timesheet.act_hr_timesheet_line', 'dolan_grid',
     {'string': 'Grilla', 'row_field': 'project_id', 'date_field': 'date', 'measure': 'unit_amount', 'range': 'week',
      'editable': '1'}),
    ('mrp.production', 'mrp.mrp_production_action', 'dolan_gantt',
     {'string': 'Planificación', 'date_start': 'date_start', 'date_stop': 'date_finished',
      'default_group_by': 'product_id'}),
    ('fleet.vehicle.log.contract', 'fleet.fleet_vehicle_log_contract_action', 'dolan_gantt',
     {'string': 'Contratos', 'date_start': 'start_date', 'date_stop': 'expiration_date',
      'default_group_by': 'vehicle_id', 'default_scale': 'year'}),
    ('dolan.rental.order', 'DOLAN_renting.action_dolan_rental_order', 'dolan_gantt',
     {'string': 'Planificación', 'date_start': 'pickup_date', 'date_stop': 'return_date',
      'default_group_by': 'partner_id'}),
    ('dolan.rental.order', 'DOLAN_renting.action_dolan_rental_order', 'dolan_map',
     {'string': 'Mapa', 'res_partner': 'partner_id'}),
    ('dolan.subscription', 'DOLAN_subscription.action_dolan_subscription', 'dolan_cohort',
     {'string': 'Retención', 'date_start': 'date_start', 'date_stop': 'date_end', 'interval': 'month'}),
    ('res.partner', 'contacts.action_contacts', 'dolan_map', {'string': 'Mapa'}),
    ('crm.lead', 'crm.crm_lead_action_pipeline', 'dolan_map', {'string': 'Mapa', 'res_partner': 'partner_id'}),
    ('crm.lead', 'crm.crm_lead_action_pipeline', 'dolan_cohort',
     {'string': 'Cohorte', 'date_start': 'create_date', 'date_stop': 'date_closed', 'interval': 'month'}),
    ('sale.order', 'sale.action_orders', 'dolan_map', {'string': 'Mapa', 'res_partner': 'partner_id'}),
]


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _get_view_info(self):
        return {
            'dolan_gantt': {'icon': 'format_align_left'},
            'dolan_map': {'icon': 'map'},
            'dolan_grid': {'icon': 'grid_view'},
            'dolan_cohort': {'icon': 'table_chart'},
        } | super()._get_view_info()

    def _dolan_validate_generic(self, node, view_type):
        remaining = set(node.attrib) - VALID_ATTRIBUTES[view_type] - {'__validate__', 'class', 'js_class'}
        if remaining:
            self._raise_view_error(_('Atributos inválidos en la vista %(type)s: %(attrs)s',
                                     type=view_type, attrs=', '.join(sorted(remaining))), node)
        for attribute in REQUIRED_ATTRIBUTES[view_type]:
            if not node.get(attribute):
                self._raise_view_error(_('La vista %(type)s necesita el atributo %(attr)s',
                                         type=view_type, attr=attribute), node)
        model = self.env[self.model] if self.model in self.env else None
        if model is not None:
            for attribute in FIELD_ATTRIBUTES & set(node.attrib):
                if node.get(attribute) not in model._fields:
                    self._raise_view_error(_('El campo %(field)s no existe en %(model)s',
                                             field=node.get(attribute), model=self.model), node)

    def _validate_tag_dolan_gantt(self, node, name_manager, node_info):
        if node_info['validate']:
            self._dolan_validate_generic(node, 'dolan_gantt')

    def _validate_tag_dolan_map(self, node, name_manager, node_info):
        if node_info['validate']:
            self._dolan_validate_generic(node, 'dolan_map')

    def _validate_tag_dolan_grid(self, node, name_manager, node_info):
        if node_info['validate']:
            self._dolan_validate_generic(node, 'dolan_grid')

    def _validate_tag_dolan_cohort(self, node, name_manager, node_info):
        if node_info['validate']:
            self._dolan_validate_generic(node, 'dolan_cohort')

    # ------------------------------------------------------------------
    # Registro en las apps instaladas
    # ------------------------------------------------------------------
    @api.model
    def _dolan_register_generic_views(self):
        """Crea las vistas genéricas en las apps instaladas y las suma a sus acciones. Es idempotente."""
        IMD = self.env['ir.model.data'].sudo()
        View = self.sudo()
        changed = 0
        for model_name, action_xmlid, view_type, attrs in DEFAULT_REGISTRATIONS:
            if model_name not in self.env:
                continue
            action = self.env.ref(action_xmlid, raise_if_not_found=False)
            if not action or action._name != 'ir.actions.act_window' or action.res_model != model_name:
                continue
            model_fields = self.env[model_name]._fields
            if any(attrs.get(key) and attrs[key] not in model_fields for key in FIELD_ATTRIBUTES):
                continue
            xml_name = 'generic_%s_%s' % (model_name.replace('.', '_'), view_type)
            view = self.env.ref('DOLAN_views.%s' % xml_name, raise_if_not_found=False)
            if not view:
                node = etree.Element(view_type, attrib=attrs)
                view = View.create({
                    'name': '%s.%s' % (model_name, view_type),
                    'model': model_name,
                    'type': view_type,
                    'arch': etree.tostring(node, encoding='unicode'),
                    'priority': 90,
                })
                IMD.create({'module': 'DOLAN_views', 'name': xml_name, 'model': 'ir.ui.view',
                            'res_id': view.id, 'noupdate': True})
                changed += 1
            modes = action.view_mode.split(',')
            if view_type not in modes:
                action.sudo().view_mode = ','.join(modes + [view_type])
                changed += 1
        return changed

    @api.model
    def _dolan_unregister_generic_views(self):
        """Quita los modos genéricos de todas las acciones (desinstalación)."""
        actions = self.env['ir.actions.act_window'].sudo().with_context(active_test=False).search([
            '|', '|', '|',
            ('view_mode', 'like', 'dolan_gantt'), ('view_mode', 'like', 'dolan_map'),
            ('view_mode', 'like', 'dolan_grid'), ('view_mode', 'like', 'dolan_cohort'),
        ])
        for action in actions:
            modes = [mode for mode in action.view_mode.split(',') if mode not in GENERIC_TYPES]
            action.view_mode = ','.join(modes) or 'list,form'
        self.env['ir.actions.act_window.view'].sudo().search([('view_mode', 'in', GENERIC_TYPES)]).unlink()

    def _register_hook(self):
        super()._register_hook()
        module = self.env['ir.module.module'].sudo().search([('name', '=', 'DOLAN_views')], limit=1)
        if module.state != 'installed':
            return
        try:
            with self.env.cr.savepoint():
                if self._dolan_register_generic_views():
                    _logger.info('DOLAN_views: vistas genéricas registradas en las apps instaladas')
        except Exception:  # noqa: BLE001 - nunca frenar el arranque del servidor por esto
            _logger.exception('DOLAN_views: no se pudieron registrar las vistas genéricas')
