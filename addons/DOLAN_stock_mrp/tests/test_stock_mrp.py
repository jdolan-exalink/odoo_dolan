# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDolanStockMrp(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.stock_location = cls.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, cls.company.id]),
        ], limit=1)
        cls.customer_location = cls.env['stock.location'].search([
            ('usage', '=', 'customer'),
        ], limit=1)
        cls.picking_type_out = cls.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('company_id', 'in', [False, cls.company.id]),
        ], limit=1)

        cls.product = cls.env['product.product'].create({
            'name': 'Componente de Precisión CNC',
            'is_storable': True,
            'barcode': '7791234567890',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Operario Juan Pérez',
            'company_id': cls.company.id,
        })
        cls.workcenter = cls.env['mrp.workcenter'].create({
            'name': 'Centro de Mecanizado 01',
            'time_efficiency': 100.0,
            'company_id': cls.company.id,
        })
        cls.equipment = cls.env['maintenance.equipment'].create({
            'name': 'Torno Haas CNC 01',
            'company_id': cls.company.id,
        })

    def test_01_stock_barcode_session(self):
        """Valida que una sesión de código de barras procese productos correctamente."""
        session = self.env['dolan.stock.barcode.session'].create({
            'operation_mode': 'inventory',
            'location_id': self.stock_location.id,
        })
        self.assertEqual(session.state, 'in_progress')

        # Escanear el código de barras del producto
        session.barcode_input = self.product.barcode
        session.action_process_barcode()

        self.assertEqual(session.last_scan_status, 'ok')
        self.assertEqual(len(session.line_ids), 1)
        line = session.line_ids[0]
        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.scanned_qty, 1.0)

        # Escanear el mismo producto nuevamente: debe sumar cantidad
        session.barcode_input = self.product.barcode
        session.action_process_barcode()
        self.assertEqual(len(session.line_ids), 1)
        self.assertEqual(line.scanned_qty, 2.0)

        # Validar sesión
        session.action_validate_session()
        self.assertEqual(session.state, 'done')

    def test_02_shopfloor_workorder_and_labor_cost(self):
        """Valida registro de horas de operario y cálculo de costo horario en taller."""
        # Crear orden de fabricación mínima
        production = self.env['mrp.production'].create({
            'product_id': self.product.id,
            'product_qty': 5.0,
            'company_id': self.company.id,
        })
        workorder = self.env['mrp.workorder'].create({
            'name': 'Fresado CNC Fase 1',
            'workcenter_id': self.workcenter.id,
            'production_id': production.id,
            'shopfloor_employee_id': self.employee.id,
            'equipment_id': self.equipment.id,
        })

        # Iniciar tiempo de operario (2 horas = 120 minutos a $30/h)
        start_time = fields.Datetime.now() - timedelta(hours=2)
        end_time = fields.Datetime.now()
        work_time = self.env['dolan.mrp.workorder.time'].create({
            'workorder_id': workorder.id,
            'employee_id': self.employee.id,
            'hourly_cost': 30.0,
            'date_start': start_time,
            'date_end': end_time,
        })

        self.assertAlmostEqual(work_time.duration_minutes, 120.0, delta=1.0)
        self.assertAlmostEqual(work_time.labor_cost_total, 60.0, delta=1.0)
        self.assertAlmostEqual(workorder.total_labor_cost, 60.0, delta=1.0)

        # Probar solicitud de mantenimiento desde la orden de trabajo
        action = workorder.action_create_maintenance_request()
        self.assertTrue(action)
        self.assertGreaterEqual(workorder.maintenance_request_count, 1)

    def test_03_quality_control_and_alert(self):
        """Valida chequeos de calidad dimensionales con tolerancia y alertas CAPA."""
        # QCP con tolerancia [9.5, 10.5]
        qcp = self.env['dolan.quality.point'].create({
            'title': 'Diámetro de Eje CNC',
            'test_type': 'measure',
            'norm': 10.0,
            'tolerance_min': 9.5,
            'tolerance_max': 10.5,
            'picking_type_ids': [(6, 0, [self.picking_type_out.id])],
            'product_ids': [(6, 0, [self.product.id])],
        })

        # Control 1: Valor 10.1 (dentro de tolerancia) -> pasa
        check_ok = self.env['dolan.quality.check'].create({
            'point_id': qcp.id,
            'product_id': self.product.id,
            'measure': 10.1,
            'tolerance_min': 9.5,
            'tolerance_max': 10.5,
            'test_type': 'measure',
        })
        check_ok.action_evaluate_measure()
        self.assertEqual(check_ok.quality_state, 'pass')

        # Control 2: Valor 11.2 (fuera de tolerancia) -> falla
        check_fail = self.env['dolan.quality.check'].create({
            'point_id': qcp.id,
            'product_id': self.product.id,
            'measure': 11.2,
            'tolerance_min': 9.5,
            'tolerance_max': 10.5,
            'test_type': 'measure',
        })
        check_fail.action_evaluate_measure()
        self.assertEqual(check_fail.quality_state, 'fail')

        # Generar alerta de no conformidad
        res = check_fail.action_create_quality_alert()
        self.assertTrue(res)
        alert = self.env['dolan.quality.alert'].browse(res['res_id'])
        self.assertEqual(alert.check_id, check_fail)
        self.assertEqual(alert.product_id, self.product)
