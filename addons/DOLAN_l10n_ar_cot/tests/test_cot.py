# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import re
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.addons.DOLAN_l10n_ar_cot.models.cot_service import DolanCotService, split_street

OK_RESPONSE = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<TBCOMPROBANTE>
  <cuitEmpresa>30111111118</cuitEmpresa>
  <numeroComprobante>123</numeroComprobante>
  <nombreArchivo>TB.txt</nombreArchivo>
  <codigoIntegridad>ABC</codigoIntegridad>
  <validacionesRemitos>
    <remito>
      <numeroUnico>%s</numeroUnico>
      <procesado>SI</procesado>
      <cot>2000000123456789</cot>
    </remito>
  </validacionesRemitos>
</TBCOMPROBANTE>"""

ERROR_RESPONSE = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<TBCOMPROBANTE>
  <validacionesRemitos>
    <remito>
      <numeroUnico>%s</numeroUnico>
      <procesado>NO</procesado>
      <errores><error><codigoError>12</codigoError><mensajeError>Domicilio de destino invalido</mensajeError></error></errores>
    </remito>
  </validacionesRemitos>
</TBCOMPROBANTE>"""


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestDolanCot(TestArCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.state_ba = cls.env.ref('base.state_ar_b')
        cls.state_cba = cls.env.ref('base.state_ar_x')
        cls.state_sf = cls.env.ref('base.state_ar_s')
        cls.company.write({
            'dolan_cot_enabled': True,
            'dolan_cot_user': cls.company.vat,
            'dolan_cot_password': 'cit-de-prueba',
            'dolan_cot_plant': '1',
            'dolan_cot_min_amount': 0.0,
        })
        cls.company.partner_id.write({
            'street': 'Calle 7 1234', 'city': 'La Plata', 'zip': '1900', 'state_id': cls.state_ba.id,
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'Cliente Lomas SRL', 'is_company': True, 'vat': '30714295698',
            'l10n_ar_afip_responsibility_type_id': cls.env.ref('l10n_ar.res_IVARI').id,
            'street': 'Av. Siempre Viva 742', 'city': 'Lomas de Zamora', 'zip': 'B1832',
            'state_id': cls.state_ba.id, 'country_id': cls.env.ref('base.ar').id,
        })
        cls.wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.wh.partner_id = cls.company.partner_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.product = cls.env['product.product'].create({
            'name': 'Notebook 14"', 'default_code': 'NB14', 'type': 'consu',
            'list_price': 500000.0, 'dolan_cot_code': '847130',
        })
        cls.picking_type = cls.env['stock.picking.type'].create({
            'name': 'Remito R', 'code': 'outgoing', 'company_id': cls.company.id,
            'sequence_code': 'RTO', 'warehouse_id': cls.wh.id,
            'default_location_src_id': cls.wh.lot_stock_id.id,
            'default_location_dest_id': cls.customer_location.id,
            'l10n_ar_document_type_id': cls.env.ref('l10n_ar.dc_r_r').id,
            'l10n_ar_cai_authorization_code': '12345678901234',
            'l10n_ar_cai_expiration_date': '2099-12-31',
            'l10n_ar_sequence_number_start': '00000001',
            'l10n_ar_sequence_number_end': '00000999',
        })
        cls.carrier = cls.env['res.partner'].create({'name': 'Transportes Sur SA', 'vat': '30500010912'})

    def _picking(self, product=None, qty=2.0, partner=None):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type.id,
            'location_id': self.wh.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
            'partner_id': (partner or self.customer).id,
            'dolan_cot_carrier_id': self.carrier.id,
            'dolan_cot_vehicle_plate': 'AB 123 CD',
            'move_ids': [Command.create({
                'product_id': (product or self.product).id,
                'product_uom_qty': qty,
                'location_id': self.wh.lot_stock_id.id,
                'location_dest_id': self.customer_location.id,
            })],
        })
        picking.action_confirm()
        picking.button_validate()
        return picking

    def _patch_post(self, response=None, side_effect=None):
        def fake_post(service, company, filename, content):
            fake_post.calls.append((filename, content))
            if side_effect:
                raise side_effect
            return response(fake_post.calls) if callable(response) else response
        fake_post.calls = []
        return patch.object(DolanCotService, '_post', fake_post), fake_post

    def test_01_split_street_and_required(self):
        self.assertEqual(split_street('Av. Siempre Viva 742'), ('Av. Siempre Viva', '742'))
        self.assertEqual(split_street('Ruta 2 km'), ('Ruta 2 km', 'S/N'))
        picking = self._picking()
        self.assertEqual(picking.state, 'done')
        self.assertAlmostEqual(picking.dolan_cot_amount, 1000000.0)
        self.assertTrue(picking.dolan_cot_required)
        self.company.dolan_cot_min_amount = 2000000.0
        picking.invalidate_recordset(['dolan_cot_required'])
        self.assertFalse(picking.dolan_cot_required, 'Bajo el mínimo no requiere COT')
        self.company.dolan_cot_min_amount = 0.0
        self.company.partner_id.state_id = self.state_sf
        cordoba = self.customer.copy({'state_id': self.state_cba.id})
        other = self._picking(partner=cordoba)
        self.assertFalse(other.dolan_cot_required, 'Santa Fe a Córdoba no pasa por PBA')

    def test_02_build_file(self):
        picking = self._picking()
        picking.l10n_ar_action_create_delivery_guide()
        code = picking._dolan_cot_unique_code()
        self.assertRegex(code, r'^091R\d{4}\d{8}$')
        filename, content = self.env['dolan.cot.service'].build_file(picking)
        cuit = re.sub(r'\D', '', self.company.vat)
        self.assertRegex(filename, r'^TB_%s_000001_\d{8}_000001\.txt$' % cuit)
        lines = content.split('\r\n')[:-1]
        self.assertEqual(lines[0], '01|%s' % cuit)
        remito = lines[1].split('|')
        self.assertEqual(remito[0], '02')
        self.assertEqual(remito[2], code)
        self.assertEqual(remito[9], '30714295698')
        self.assertEqual(remito[10], 'Cliente Lomas SRL')
        self.assertIn('B1832', remito)
        self.assertIn('Av. Siempre Viva', remito)
        self.assertIn('742', remito)
        self.assertIn('B', remito)
        self.assertIn('30500010912', remito)
        self.assertIn('AB123CD', remito)
        self.assertEqual(remito[-1], '1000000.00')
        product = lines[2].split('|')
        self.assertEqual(product[:4], ['03', '847130', '7', '2.00'])
        self.assertEqual(lines[3], '04|1')

    def test_03_request_ok_and_report(self):
        picking = self._picking()
        picking.l10n_ar_action_create_delivery_guide()
        code = picking._dolan_cot_unique_code()
        patcher, fake = self._patch_post(OK_RESPONSE % code.encode())
        with patcher:
            picking.action_dolan_request_cot()
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(picking.dolan_cot_state, 'done')
        self.assertEqual(picking.dolan_cot_number, '2000000123456789')
        self.assertTrue(picking.dolan_cot_file_id.name.startswith('TB_'))
        with self.assertRaises(UserError):
            picking.action_dolan_request_cot()
        arch = self.env.ref('l10n_ar_stock.report_delivery_document').get_combined_arch()
        self.assertIn('o.dolan_cot_number', arch, 'El remito impreso muestra el COT')

    def test_04_request_rejected(self):
        picking = self._picking()
        picking.l10n_ar_action_create_delivery_guide()
        patcher, __ = self._patch_post(ERROR_RESPONSE % picking._dolan_cot_unique_code().encode())
        with patcher:
            action = picking.action_dolan_request_cot()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertEqual(picking.dolan_cot_state, 'error')
        self.assertIn('Domicilio de destino invalido', picking.dolan_cot_message)

    def test_05_batch_one_file(self):
        first, second = self._picking(), self._picking()
        pickings = first | second
        pickings.l10n_ar_action_create_delivery_guide()

        def response(calls):
            return b'<TBCOMPROBANTE><validacionesRemitos>' + b''.join(
                b'<remito><numeroUnico>%s</numeroUnico><procesado>SI</procesado><cot>%d</cot></remito>'
                % (p._dolan_cot_unique_code().encode(), 900 + i) for i, p in enumerate(pickings)
            ) + b'</validacionesRemitos></TBCOMPROBANTE>'

        patcher, fake = self._patch_post(response)
        with patcher:
            pickings.action_dolan_request_cot()
        self.assertEqual(len(fake.calls), 1, 'Un solo archivo para los remitos seleccionados')
        self.assertTrue(fake.calls[0][1].endswith('04|2\r\n'))
        self.assertEqual(pickings.mapped('dolan_cot_number'), ['900', '901'])

    def test_06_missing_product_code(self):
        product = self.product.copy({'dolan_cot_code': False, 'name': 'Sin código'})
        picking = self._picking(product=product)
        picking.l10n_ar_action_create_delivery_guide()
        with self.assertRaisesRegex(UserError, 'Sin código'):
            self.env['dolan.cot.service'].build_file(picking)

    def test_07_auto_on_delivery_guide(self):
        self.company.dolan_cot_auto = True
        picking = self._picking()
        patcher, fake = self._patch_post(lambda calls: OK_RESPONSE % picking._dolan_cot_unique_code().encode())
        with patcher:
            picking.l10n_ar_action_create_delivery_guide()
        self.assertTrue(picking.l10n_ar_delivery_guide_number)
        self.assertEqual(picking.dolan_cot_state, 'done')

        failing = self._picking()
        patcher, __ = self._patch_post(side_effect=UserError('ARBA fuera de servicio'))
        with patcher:
            failing.l10n_ar_action_create_delivery_guide()
        self.assertTrue(failing.l10n_ar_delivery_guide_number, 'El remito se numera aunque falle el COT')
        self.assertEqual(failing.dolan_cot_state, 'error')
        self.assertIn('fuera de servicio', failing.dolan_cot_message)
