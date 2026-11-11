# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestDolanGenericViews(TransactionCase):

    def test_registered_on_project_tasks(self):
        View = self.env['ir.ui.view']
        View._dolan_register_generic_views()
        action = self.env.ref('project.action_view_all_task')
        modes = action.view_mode.split(',')
        for mode in ('dolan_gantt', 'dolan_map', 'dolan_cohort'):
            self.assertIn(mode, modes)
        gantt = self.env.ref('DOLAN_views.generic_project_task_dolan_gantt')
        self.assertEqual(gantt.type, 'dolan_gantt')
        self.assertIn('date_deadline', gantt.arch)
        # Idempotente: una segunda pasada no cambia nada.
        self.assertEqual(View._dolan_register_generic_views(), 0)
        self.assertEqual(len(action.view_mode.split(',')), len(set(action.view_mode.split(','))))

    def test_get_views_and_view_info(self):
        self.env['ir.ui.view']._dolan_register_generic_views()
        result = self.env['project.task'].get_views([[False, 'dolan_gantt'], [False, 'dolan_map']])
        self.assertIn('dolan_gantt', result['views'])
        self.assertIn('<dolan_gantt', result['views']['dolan_gantt']['arch'])
        info = self.env['ir.ui.view'].get_view_info()
        self.assertEqual(info['dolan_gantt']['icon'], 'format_align_left')
        self.assertTrue(info['dolan_map']['multi_record'])

    def test_custom_view_on_any_model(self):
        view = self.env['ir.ui.view'].create({
            'name': 'res.partner.dolan_cohort.test',
            'model': 'res.partner',
            'type': 'dolan_cohort',
            'arch': '<dolan_cohort date_start="create_date" interval="week"/>',
        })
        self.assertEqual(view.type, 'dolan_cohort')

    @mute_logger('odoo.addons.base.models.ir_ui_view')
    def test_arch_validation(self):
        View = self.env['ir.ui.view']
        with self.assertRaises(Exception):
            View.create({'name': 'x', 'model': 'project.task', 'type': 'dolan_gantt',
                         'arch': '<dolan_gantt date_start="campo_inexistente"/>'})
        with self.assertRaises(Exception):
            View.create({'name': 'x', 'model': 'project.task', 'type': 'dolan_grid',
                         'arch': '<dolan_grid row_field="project_id" date_field="date_deadline"/>'})
        with self.assertRaises(Exception):
            View.create({'name': 'x', 'model': 'project.task', 'type': 'dolan_map',
                         'arch': '<dolan_map atributo_raro="1"/>'})

    def test_unregister(self):
        View = self.env['ir.ui.view']
        View._dolan_register_generic_views()
        View._dolan_unregister_generic_views()
        action = self.env.ref('project.action_view_all_task')
        self.assertFalse({'dolan_gantt', 'dolan_map', 'dolan_cohort'} & set(action.view_mode.split(',')))
