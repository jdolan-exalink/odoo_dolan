import io
import json
import zipfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..services.catalog_resolver import CatalogResolver
from ..services.exporter_registry import ScaleExporter
from ..services.price_resolver import PriceResolver


class SyntheticScaleExporter(ScaleExporter):
    """Test-only adapter; its output is never presented as a real device format."""

    adapter_code = 'synthetic_test'

    def serialize(self, records, profile):
        return 'synthetic_test.dat', ('TEST ONLY\n' + str(len(records))).encode()


@tagged('post_install', '-at_install')
class TestScaleManagement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.write({'group_ids': [(4, cls.env.ref('pos_scale_management.group_scale_admin').id)]})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env['stock.warehouse'].create({
                'name': 'Balanza QA', 'code': 'SQA', 'company_id': cls.company.id,
            })
        cls.profile = cls.env.ref('pos_scale_management.profile_kretz_itegra_draft')
        cls.device = cls.env['scale.device'].create({
            'name': 'Balanza QA', 'code': 'QA01', 'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id, 'brand': 'kretz', 'model_name': 'Fixture sintético',
            'profile_id': cls.profile.id,
        })

    def _make_product(self, name, category):
        template = self.env['product.template'].create({
            'name': name,
            'categ_id': category.id,
            'sale_ok': True,
            'available_in_pos': True,
            'list_price': 1250.0,
        })
        return template.product_variant_id

    def test_explicit_exclusion_wins_category_include(self):
        category = self.env['product.category'].create({'name': 'Carnes QA'})
        product = self._make_product('Producto fixture', category)
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'category',
            'category_id': category.id, 'disposition': 'include',
        })
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'product',
            'product_id': product.id, 'disposition': 'exclude',
        })
        self.assertNotIn(product, CatalogResolver(self.device).resolve())

    def test_price_override_has_priority_and_snapshot_reports_source(self):
        category = self.env['product.category'].create({'name': 'QA precios'})
        product = self._make_product('Producto precio QA', category)
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'product',
            'product_id': product.id, 'disposition': 'include', 'plu': '72001',
        })
        standard = PriceResolver(self.device).resolve(product)
        self.assertEqual(standard[product.id]['price'], 1250.0)
        self.assertEqual(standard[product.id]['source'], 'Precio de venta estándar')

        self.env['scale.price.override'].create({
            'device_id': self.device.id, 'product_id': product.id,
            'price': 1899.5, 'currency_id': self.company.currency_id.id,
        })
        overridden = PriceResolver(self.device).resolve(product)
        self.assertEqual(overridden[product.id]['price'], 1899.5)
        self.assertEqual(overridden[product.id]['source'], 'Excepción de balanza')

    def test_draft_itegra_profile_never_generates_file(self):
        category = self.env['product.category'].create({'name': 'Venta QA'})
        product = self._make_product('Producto con PLU QA', category)
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'product',
            'product_id': product.id, 'disposition': 'include', 'plu': '12345',
        })
        job = self.env['scale.export.job'].create_export(self.device)
        self.assertEqual(job.state, 'blocked')
        self.assertFalse(job.file_data)
        self.assertIn('iTegra', job.error_report)
        with self.assertRaises(UserError):
            job.write({'snapshot_json': '{}'})
        with self.assertRaises(UserError):
            job.with_context(scale_internal_file_generation=True).write({'file_name': 'fake.csv'})
        with self.assertRaises(UserError):
            self.profile.write({'validation_state': 'validated'})

    def test_barcode_profile_interprets_configured_weight(self):
        profile = self.env['scale.barcode.profile'].create({
            'name': 'Fixture sin etiqueta comercial', 'code': 'SYNTHETIC_QA',
            'barcode_length': 13, 'prefix': '20',
            'product_start': 3, 'product_length': 5,
            'value_start': 8, 'value_length': 5,
            'value_type': 'weight', 'decimals': 2,
        })
        parsed = profile.interpret('2012345001250')
        self.assertEqual(parsed['product_code'], '12345')
        self.assertEqual(parsed['value_type'], 'weight')
        self.assertEqual(parsed['value'], 1.25)

    def test_pos_receives_branch_label_profile_and_rejects_ambiguous_plu(self):
        category = self.env['product.category'].create({'name': 'QA etiqueta POS'})
        first = self._make_product('Carne A QA', category)
        second = self._make_product('Carne B QA', category)
        barcode_profile = self.env['scale.barcode.profile'].create({
            'name': 'Fixture etiqueta POS', 'code': 'POS_SCALE_QA',
            'barcode_length': 13, 'prefix': '20', 'product_start': 3,
            'product_length': 5, 'value_start': 8, 'value_length': 5,
            'value_type': 'weight', 'decimals': 3,
        })
        self.device.write({'barcode_profile_id': barcode_profile.id})
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'product',
            'product_id': first.id, 'disposition': 'include', 'plu': '12345',
        })
        second_device = self.env['scale.device'].create({
            'name': 'Balanza QA 2', 'code': 'QA-LABEL-2', 'company_id': self.company.id,
            'warehouse_id': self.warehouse.id, 'brand': 'kretz', 'profile_id': self.profile.id,
            'barcode_profile_id': barcode_profile.id,
        })
        self.env['scale.product.assignment'].create({
            'device_id': second_device.id, 'assignment_type': 'product',
            'product_id': second.id, 'disposition': 'include', 'plu': '12345',
        })
        config = self.env['pos.config'].create({
            'name': 'Caja etiqueta QA', 'company_id': self.company.id,
            'picking_type_id': self.warehouse.out_type_id.id,
        })
        pos_fields = config._load_pos_data_fields(config)
        for name in ('use_pricelist', 'trusted_config_ids', 'floor_plan', 'scale_barcode_profiles'):
            self.assertIn(name, pos_fields)
        payload = config.scale_barcode_profiles
        self.assertEqual(len(payload), 1)
        self.assertIs(payload[0]['products']['12345'], False)

    def test_validated_generic_adapter_generates_immutable_audited_file(self):
        category = self.env['product.category'].create({'name': 'QA exportación'})
        product = self._make_product('Producto exportación QA', category)
        profile = self.env['scale.export.profile'].create({
            'name': 'Adaptador sintético de pruebas', 'code': 'SYNTHETIC_TEST',
            'brand': 'other', 'adapter_code': 'synthetic_test', 'format_version': 'fixture-1',
            'itegra_version': 'N/A - prueba automatizada',
            'validation_note': 'Fixture sintético, no representa un formato comercial.',
            'evidence_attachment_id': self.env['ir.attachment'].create({
                'name': 'synthetic-fixture.txt', 'type': 'binary',
                'raw': b'TEST ONLY',
            }).id,
        })
        profile.action_mark_validated()
        self.device.write({'brand': 'other', 'profile_id': profile.id})
        self.env['scale.product.assignment'].create({
            'device_id': self.device.id, 'assignment_type': 'product',
            'product_id': product.id, 'disposition': 'include', 'plu': '70001',
        })

        job = self.env['scale.export.job'].create_export(self.device)
        self.assertEqual(job.state, 'generated')
        self.assertEqual(job.file_name, 'synthetic_test.dat')
        self.assertTrue(job.checksum_sha256)
        with self.assertRaises(UserError):
            job.write({'state': 'downloaded'})
        self.assertIn('/pos_scale_management/export/', job.action_download()['url'])
        job._mark_downloaded()
        self.assertEqual(job.state, 'downloaded')
    def test_branch_zip_aborts_as_a_unit_or_contains_manifest(self):
        category = self.env['product.category'].create({'name': 'QA lote'})
        product = self._make_product('Producto lote QA', category)
        profile = self.env['scale.export.profile'].create({
            'name': 'Adaptador sintético de lote', 'code': 'SYNTHETIC_BATCH',
            'brand': 'other', 'adapter_code': 'synthetic_test', 'format_version': 'fixture-1',
            'itegra_version': 'N/A - prueba automatizada',
            'validation_note': 'Fixture sintético, no representa un formato comercial.',
            'evidence_attachment_id': self.env['ir.attachment'].create({
                'name': 'synthetic-fixture.txt', 'type': 'binary', 'raw': b'TEST ONLY',
            }).id,
        })
        profile.action_mark_validated()
        self.device.write({'brand': 'other', 'profile_id': profile.id})
        for device in self.device:
            self.env['scale.product.assignment'].create({
                'device_id': device.id, 'assignment_type': 'product',
                'product_id': product.id, 'disposition': 'include', 'plu': '71001',
            })
        self.env['scale.device'].create({
            'name': 'Balanza QA 2', 'code': 'QA02', 'company_id': self.company.id,
            'warehouse_id': self.warehouse.id, 'brand': 'other', 'profile_id': profile.id,
        })
        second = self.env['scale.device'].search([('code', '=', 'QA02')], limit=1)
        self.env['scale.product.assignment'].create({
            'device_id': second.id, 'assignment_type': 'product',
            'product_id': product.id, 'disposition': 'include', 'plu': '71002',
        })

        batch = self.env['scale.export.job'].create_branch_export(self.warehouse)
        self.assertEqual(batch.job_type, 'branch_zip')
        self.assertEqual(batch.state, 'generated')
        with zipfile.ZipFile(io.BytesIO(batch.file_data.content)) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['files']), 2)
