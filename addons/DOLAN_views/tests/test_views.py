# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestDolanViews(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.user = cls.env.user
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Vista Geolocalizada S.A.',
            'street': 'Av. Corrientes 1234',
            'city': 'Buenos Aires',
            'is_company': True,
        })

    def test_01_duration_and_constraints(self):
        """Valida cálculo de horas de duración y validación de fechas/progreso."""
        now = fields.Datetime.now()
        item = self.env['dolan.view.planner.item'].create({
            'name': 'Fase 1: Implementación de Infraestructura',
            'category_type': 'project',
            'date_start': now,
            'date_stop': now + timedelta(hours=48),
            'progress': 50.0,
        })
        self.assertAlmostEqual(item.duration_hours, 48.0, delta=0.5)

        # Fecha de fin anterior a inicio -> ValidationError
        with self.assertRaises(ValidationError):
            self.env['dolan.view.planner.item'].create({
                'name': 'Error Fecha',
                'date_start': now,
                'date_stop': now - timedelta(days=1),
            })

        # Progreso mayor a 100 -> ValidationError
        with self.assertRaises(ValidationError):
            self.env['dolan.view.planner.item'].create({
                'name': 'Error Progreso',
                'date_start': now,
                'date_stop': now + timedelta(days=1),
                'progress': 150.0,
            })

    def test_02_gantt_dependencies_and_multiview_payload(self):
        """Valida dependencias de Gantt y generación de payload unificado para OWL 3 (Gantt, Grid, Map, Cohort)."""
        today = fields.Date.context_today(self)
        monday = today - timedelta(days=today.weekday())
        # Anchor the fixture inside the selected week so the weekly grid stays
        # deterministic when the test runs on Saturday or Sunday.
        now = fields.Datetime.to_datetime(monday) + timedelta(hours=10)
        item_a = self.env['dolan.view.planner.item'].create({
            'name': 'Tarea A: Diseño de Arquitectura',
            'category_type': 'project',
            'user_id': self.user.id,
            'partner_id': self.partner.id,
            'date_start': now,
            'date_stop': now + timedelta(days=2),
            'worked_hours': 16.0,
            'latitude': -34.6037,
            'longitude': -58.3816,
            'state': 'done',
        })

        item_b = self.env['dolan.view.planner.item'].create({
            'name': 'Tarea B: Construcción y Pruebas',
            'category_type': 'project',
            'user_id': self.user.id,
            'date_start': now + timedelta(days=2),
            'date_stop': now + timedelta(days=5),
            'dependency_ids': [(6, 0, [item_a.id])],
            'worked_hours': 24.0,
            'state': 'in_progress',
        })

        self.assertIn(item_a, item_b.dependency_ids)

        # Ejecutar generador de datos para componentes OWL 3
        data = self.env['dolan.view.planner.item'].get_multiview_dashboard_data('all', 'week')
        self.assertIn('gantt_rows', data)
        self.assertIn('grid_rows', data)
        self.assertIn('map_markers', data)
        self.assertIn('cohort_rows', data)

        # Validar filas de Gantt
        gantt_names = [row['name'] for row in data['gantt_rows']]
        self.assertIn('Tarea A: Diseño de Arquitectura', gantt_names)
        self.assertIn('Tarea B: Construcción y Pruebas', gantt_names)

        # Validar marcadores de mapa
        self.assertTrue(len(data['map_markers']) >= 1)
        first_marker = data['map_markers'][0]
        self.assertIn('osm_url', first_marker)
        self.assertTrue(first_marker.get('lat'))

        # Validar Grid de horas
        self.assertTrue(len(data['grid_rows']) >= 1)
        grid_total = sum(g['total'] for g in data['grid_rows'])
        self.assertGreaterEqual(grid_total, 40.0)

        # Validar Cohort
        self.assertTrue(len(data['cohort_rows']) >= 1)
