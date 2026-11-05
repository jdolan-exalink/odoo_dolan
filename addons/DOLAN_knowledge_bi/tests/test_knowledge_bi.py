# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

from datetime import date
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestDolanKnowledgeBi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.user = cls.env.user

    def test_01_knowledge_article_hierarchy_and_permissions(self):
        """Valida estructura jerárquica de artículos, full_path, bloqueo y categorías."""
        # 1. Crear artículo raíz
        root_article = self.env['dolan.knowledge.article'].create({
            'name': 'Manual de Operaciones y Políticas',
            'icon': '📘',
            'category': 'workspace',
            'company_id': self.company.id,
            'body': '<p>Contenido principal de la empresa.</p>',
        })
        self.assertEqual(root_article.child_count, 0)
        self.assertEqual(root_article.full_path, '📘 Manual de Operaciones y Políticas')

        # 2. Crear sub-artículo
        child_article = self.env['dolan.knowledge.article'].create({
            'name': 'Procedimiento de Ventas',
            'icon': '💼',
            'parent_id': root_article.id,
            'category': 'workspace',
            'company_id': self.company.id,
            'body': '<p>Guía paso a paso para el equipo comercial.</p>',
        })
        root_article._compute_child_count()
        self.assertEqual(root_article.child_count, 1)
        self.assertEqual(child_article.parent_id, root_article)
        self.assertEqual(child_article.full_path, '📘 Manual de Operaciones y Políticas / 💼 Procedimiento de Ventas')

        # 3. Probar bloqueo / edición
        child_article.action_toggle_lock()
        self.assertTrue(child_article.is_locked)
        child_article.action_toggle_lock()
        self.assertFalse(child_article.is_locked)

        # 4. Probar favoritos
        child_article.action_toggle_favorite()
        self.assertTrue(child_article.is_favorite)

    def test_02_bi_dashboard_metrics_and_export(self):
        """Valida cálculo de métricas en tiempo real del tablero BI y tarjetas KPI."""
        dashboard = self.env['dolan.bi.dashboard'].create({
            'name': 'Tablero Gerencial de Prueba',
            'code': 'TEST_EXEC',
            'dashboard_type': 'executive',
            'company_id': self.company.id,
            'date_from': date.today().replace(day=1),
            'date_to': date.today(),
        })

        # Crear tarjeta KPI vinculada
        kpi = self.env['dolan.bi.kpi.card'].create({
            'name': 'Ventas Mensuales',
            'dashboard_id': dashboard.id,
            'metric_type': 'sales_month',
            'target_value': 100000.0,
        })

        # Recalcular métricas
        dashboard._compute_realtime_metrics()
        kpi._compute_current_value()

        self.assertIsNotNone(dashboard.sales_month)
        self.assertIsNotNone(dashboard.receivables_due)
        self.assertIsNotNone(dashboard.payables_due)
        self.assertIsNotNone(dashboard.net_cash_position)
        self.assertEqual(kpi.current_value, dashboard.sales_month)

        # Validar generación de URL de exportación XLSX
        action_export = dashboard.action_export_xlsx()
        self.assertTrue(action_export.get('url'))
        self.assertIn('/dolan/bi/export/', action_export['url'])
