# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import xml.etree.ElementTree as ET
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


def _texts(xml, tag):
    return [(node.text or '') for node in ET.fromstring(xml).iter() if node.tag.split('}')[-1] == tag]


@tagged('post_install', '-at_install')
class TestExportAndDetailInvoices(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ar = cls.env.ref('base.ar')
        us = cls.env.ref('base.us')
        us.write({'l10n_ar_afip_code': '212', 'l10n_ar_legal_entity_vat': '55000002126'})
        company = cls.company_data['company']
        company.partner_id.with_context(no_vat_validation=True).write({'country_id': ar.id, 'vat': '30712345671'})
        company.write({'account_fiscal_country_id': ar.id})
        ars = cls.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ARS')], limit=1)
        ars.write({'active': True, 'l10n_ar_afip_code': 'PES'})
        company.currency_id = ars
        cls.usd = cls.env.ref('base.USD')
        cls.usd.write({'active': True, 'l10n_ar_afip_code': 'DOL'})
        cls.env['res.currency.rate'].create({
            'currency_id': cls.usd.id,
            'company_id': company.id,
            'name': fields.Date.today(),
            'rate': 1 / 1000.0,
        })
        cls.ri = cls.env['l10n_ar.afip.responsibility.type'].search([('code', '=', '1')], limit=1)
        company.l10n_ar_afip_responsibility_type_id = cls.ri
        cls.ars = ars
        cls.env['ir.config_parameter'].sudo().set_bool('l10n_ar_afip.wsfe_submission_enabled', True)

        cls.export_journal = cls.env['account.journal'].create({
            'name': 'Exportación', 'code': 'EXPO', 'type': 'sale', 'company_id': company.id,
            'l10n_latam_use_documents': True, 'l10n_ar_is_pos': True,
            'l10n_ar_afip_pos_number': 3, 'l10n_ar_afip_pos_system': 'DOLAN_WSFEX',
            'default_account_id': cls.company_data['default_account_revenue'].id,
        })
        cls.mtx_journal = cls.env['account.journal'].create({
            'name': 'Con detalle', 'code': 'MTX', 'type': 'sale', 'company_id': company.id,
            'l10n_latam_use_documents': True, 'l10n_ar_is_pos': True,
            'l10n_ar_afip_pos_number': 4, 'l10n_ar_afip_pos_system': 'DOLAN_WSMTXCA',
            'default_account_id': cls.company_data['default_account_revenue'].id,
        })
        foreign = cls.env['l10n_ar.afip.responsibility.type'].search([('code', '=', '9')], limit=1)
        cls.foreign_customer = cls.env['res.partner'].create({
            'name': 'Importer Inc', 'is_company': True, 'country_id': us.id,
            'street': '1 Main St', 'city': 'Miami', 'vat': '12-3456789',
            'l10n_ar_afip_responsibility_type_id': foreign.id,
        })
        cls.local_customer = cls.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente RI', 'country_id': ar.id, 'vat': '30712345672',
            'l10n_ar_afip_responsibility_type_id': cls.ri.id,
            'l10n_ar_afip_code': '80', 'l10n_ar_afip_id_value': '30712345672',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Vino Malbec', 'type': 'consu', 'default_code': 'MALBEC', 'barcode': '7790001000012',
        })
        base_tax = cls.company_data['default_tax_sale']
        group = base_tax.tax_group_id.copy({'name': 'IVA 21 MTX', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '5'})
        cls.vat21 = base_tax.copy({'name': 'IVA 21% MTX', 'amount': 21, 'tax_group_id': group.id, 'country_id': ar.id})
        exempt_group = base_tax.tax_group_id.copy({'name': 'IVA Exento EXPO', 'country_id': ar.id, 'l10n_ar_vat_afip_code': '2'})
        cls.vat_exempt = base_tax.copy({'name': 'IVA Exento EXPO', 'amount': 0, 'tax_group_id': exempt_group.id, 'country_id': ar.id})
        cls.incoterm = cls.env['account.incoterms'].search([('code', '=', 'FOB')], limit=1)
        cls.connection_fex = cls.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id, 'l10n_ar_afip_ws': 'wsfex', 'type': 'testing',
            'token': 'SYNTHETIC_TOKEN', 'sign': 'SYNTHETIC_SIGN',
        })
        cls.connection_mtx = cls.env['l10n_ar.afipws.connection'].create({
            'company_id': company.id, 'l10n_ar_afip_ws': 'wsmtxca', 'type': 'testing',
            'token': 'SYNTHETIC_TOKEN', 'sign': 'SYNTHETIC_SIGN',
        })

    def _doc(self, code, letter):
        return self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', code), ('l10n_ar_letter', '=', letter),
        ], limit=1)

    def _post_without_request(self, move):
        model = type(self.env['account.move'])
        with patch.object(model, '_l10n_ar_request_cae_wsfex'), patch.object(model, '_l10n_ar_request_cae_wsmtxca'), \
                patch.object(type(self.env['l10n_ar.afipws.connection']), 'get_active_connection',
                             return_value=self.connection_fex):
            move.action_post()
        return move

    def _export_invoice(self, **values):
        vals = {
            'move_type': 'out_invoice',
            'journal_id': self.export_journal.id,
            'partner_id': self.foreign_customer.id,
            'invoice_date': fields.Date.today(),
            'currency_id': self.usd.id,
            'l10n_latam_document_type_id': self._doc('19', 'E').id,
            'invoice_incoterm_id': self.incoterm.id,
            'l10n_ar_export_permit_existing': 'N',
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 10, 'price_unit': 50, 'discount': 10, 'tax_ids': [Command.set(self.vat_exempt.ids)],
            })],
        }
        vals.update(values)
        return self._post_without_request(self.env['account.move'].create(vals))

    # ------------------------------------------------------------------
    def test_journal_document_domains(self):
        self.assertEqual(self.export_journal.l10n_ar_afip_ws, 'wsfex')
        self.assertEqual(self.mtx_journal.l10n_ar_afip_ws, 'wsmtxca')
        self.assertEqual(self.export_journal._get_journal_codes_domain(), [('code', 'in', ['19', '20', '21'])])

    def test_wsfex_request_carries_export_data(self):
        invoice = self._export_invoice()
        self.assertRegex(invoice.l10n_latam_document_number, r'^00003-\d{8}$')
        xml = invoice._l10n_ar_build_wsfex_request_xml(self.connection_fex, 42)
        self.assertEqual(_texts(xml, 'Id'), ['42'])
        self.assertEqual(_texts(xml, 'Cbte_Tipo'), ['19'])
        self.assertEqual(_texts(xml, 'Punto_vta'), ['3'])
        self.assertEqual(_texts(xml, 'Tipo_expo'), ['1'])
        self.assertEqual(_texts(xml, 'Permiso_existente'), ['N'])
        self.assertEqual(_texts(xml, 'Dst_cmp'), ['212'])
        self.assertEqual(_texts(xml, 'Cuit_pais_cliente'), ['55000002126'])
        self.assertEqual(_texts(xml, 'Moneda_Id'), ['DOL'])
        self.assertEqual(_texts(xml, 'Moneda_ctz'), ['1000.000000'])
        self.assertEqual(_texts(xml, 'Incoterms'), ['FOB'])
        self.assertEqual(_texts(xml, 'Imp_total'), ['450.00'])
        self.assertEqual(_texts(xml, 'Pro_umed'), ['07'])
        self.assertEqual(_texts(xml, 'Pro_bonificacion'), ['50.00'])
        self.assertEqual(_texts(xml, 'Pro_total_item'), ['450.00'])
        self.assertFalse(_texts(xml, 'Fecha_pago'))

    def test_wsfex_permit_rules(self):
        invoice = self._export_invoice(l10n_ar_export_permit_existing='S', l10n_ar_export_permit_number='SHORT')
        with self.assertRaisesRegex(UserError, '16 caracteres'):
            invoice._l10n_ar_build_wsfex_request_xml(self.connection_fex, 1)
        invoice.l10n_ar_export_permit_number = '26001EC01000123A'
        xml = invoice._l10n_ar_build_wsfex_request_xml(self.connection_fex, 1)
        self.assertEqual(_texts(xml, 'Id_permiso'), ['26001EC01000123A'])
        self.assertEqual(_texts(xml, 'Dst_merc'), ['212'])

    def test_wsfex_rejects_taxes(self):
        invoice = self._export_invoice(invoice_line_ids=[Command.create({
            'product_id': self.product.id, 'quantity': 1, 'price_unit': 100, 'tax_ids': [Command.set(self.vat21.ids)],
        })])
        with self.assertRaisesRegex(UserError, 'no lleva IVA'):
            invoice._l10n_ar_build_wsfex_request_xml(self.connection_fex, 1)

    def test_wsfex_authorization_stores_cae(self):
        invoice = self._export_invoice()
        last = ET.fromstring('<E><FEXGetLast_IDResult><FEXResultGet><Id>41</Id></FEXResultGet></FEXGetLast_IDResult></E>')
        auth = ET.fromstring(
            '<E><FEXAuthorizeResult><FEXResultAuth><Id>42</Id><Cae>81234567890123</Cae>'
            '<Fch_venc_Cae>20991231</Fch_venc_Cae><Resultado>A</Resultado></FEXResultAuth>'
            '<FEXErr><ErrCode>0</ErrCode><ErrMsg>OK</ErrMsg></FEXErr></FEXAuthorizeResult></E>'
        )
        with patch.object(type(self.connection_fex), '_ws_post_envelope', side_effect=[last, auth]) as post:
            invoice._l10n_ar_request_cae_wsfex(self.connection_fex)
        self.assertEqual(post.call_args_list[1].args[1], 'wsfex')
        self.assertIn('<ar:Id>42</ar:Id>', post.call_args_list[1].args[0])
        self.assertEqual(invoice.l10n_ar_afip_auth_code, '81234567890123')
        self.assertEqual(invoice.l10n_ar_afip_result, 'A')
        self.assertIn('[REDACTED]', invoice.l10n_ar_afip_xml_request)

    def test_wsfex_rejection_never_fabricates_cae(self):
        invoice = self._export_invoice()
        last = ET.fromstring('<E><Id>1</Id></E>')
        rejected = ET.fromstring(
            '<E><FEXAuthorizeResult><FEXResultAuth><Resultado>R</Resultado></FEXResultAuth>'
            '<FEXErr><ErrCode>1561</ErrCode><ErrMsg>Permiso invalido</ErrMsg></FEXErr></FEXAuthorizeResult></E>'
        )
        with patch.object(type(self.connection_fex), '_ws_post_envelope', side_effect=[last, rejected]):
            with self.assertRaisesRegex(UserError, '1561'):
                invoice._l10n_ar_request_cae_wsfex(self.connection_fex)
        self.assertFalse(invoice.l10n_ar_afip_auth_code)

    # ------------------------------------------------------------------
    def _mtx_invoice(self, letter='A'):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': self.mtx_journal.id,
            'partner_id': self.local_customer.id,
            'invoice_date': fields.Date.today(),
            'currency_id': self.ars.id,
            'l10n_latam_document_type_id': self._doc('1' if letter == 'A' else '6', letter).id,
            'l10n_ar_afip_responsibility_type_id': self.ri.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 2, 'price_unit': 500,
                'tax_ids': [Command.set(self.vat21.ids)],
            })],
        })
        return self._post_without_request(move)

    def test_wsmtxca_a_items_disclose_vat(self):
        invoice = self._mtx_invoice('A')
        xml = invoice._l10n_ar_build_wsmtxca_request_xml(self.connection_mtx)
        self.assertEqual(_texts(xml, 'codigoTipoComprobante'), ['1'])
        self.assertEqual(_texts(xml, 'numeroPuntoVenta'), ['4'])
        self.assertEqual(_texts(xml, 'importeGravado'), ['1000.00'])
        self.assertEqual(_texts(xml, 'importeTotal'), ['1210.00'])
        self.assertEqual(_texts(xml, 'codigoMtx'), ['7790001000012'])
        self.assertEqual(_texts(xml, 'precioUnitario'), ['500.000000'])
        self.assertEqual(_texts(xml, 'importeIVA'), ['210.00'])
        self.assertEqual(_texts(xml, 'importeItem'), ['1210.00'])
        self.assertEqual(_texts(xml, 'codigo')[-1], '5')  # subtotalIVA/codigo
        self.assertEqual(_texts(xml, 'importe'), ['210.00'])
        self.assertEqual(_texts(xml, 'token'), ['SYNTHETIC_TOKEN'])

    def test_wsmtxca_b_items_include_vat_in_price(self):
        invoice = self._mtx_invoice('B')
        xml = invoice._l10n_ar_build_wsmtxca_request_xml(self.connection_mtx)
        self.assertEqual(_texts(xml, 'precioUnitario'), ['605.000000'])
        self.assertFalse(_texts(xml, 'importeIVA'))
        self.assertEqual(_texts(xml, 'importe'), ['210.00'])

    def test_wsmtxca_requires_barcode(self):
        self.product.barcode = False
        invoice = self._mtx_invoice('A')
        with self.assertRaisesRegex(UserError, 'GTIN'):
            invoice._l10n_ar_build_wsmtxca_request_xml(self.connection_mtx)

    def test_wsmtxca_authorization_and_rejection(self):
        invoice = self._mtx_invoice('A')
        rejected = ET.fromstring(
            '<E><autorizarComprobanteResponse><resultado>R</resultado><arrayErrores><codigoDescripcion>'
            '<codigo>102</codigo><descripcion>GTIN inexistente</descripcion></codigoDescripcion></arrayErrores>'
            '</autorizarComprobanteResponse></E>'
        )
        with patch.object(type(self.connection_mtx), '_ws_post_envelope', return_value=rejected):
            with self.assertRaisesRegex(UserError, '102: GTIN inexistente'):
                invoice._l10n_ar_request_cae_wsmtxca(self.connection_mtx)
        approved = ET.fromstring(
            '<E><autorizarComprobanteResponse><resultado>A</resultado><comprobanteResponse>'
            '<CAE>91234567890123</CAE><fechaVencimientoCAE>2099-12-31</fechaVencimientoCAE>'
            '</comprobanteResponse></autorizarComprobanteResponse></E>'
        )
        with patch.object(type(self.connection_mtx), '_ws_post_envelope', return_value=approved) as post:
            invoice._l10n_ar_request_cae_wsmtxca(self.connection_mtx)
        self.assertEqual(post.call_args.args[1], 'wsmtxca')
        self.assertEqual(invoice.l10n_ar_afip_auth_code, '91234567890123')
        self.assertEqual(invoice.l10n_ar_afip_auth_code_due, fields.Date.to_date('2099-12-31'))

    def test_post_dispatches_to_the_journal_service(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': self.export_journal.id,
            'partner_id': self.foreign_customer.id, 'invoice_date': fields.Date.today(),
            'currency_id': self.usd.id, 'l10n_latam_document_type_id': self._doc('19', 'E').id,
            'invoice_incoterm_id': self.incoterm.id, 'l10n_ar_export_permit_existing': 'N',
            'invoice_line_ids': [Command.create({'product_id': self.product.id, 'quantity': 1, 'price_unit': 10, 'tax_ids': [Command.set(self.vat_exempt.ids)]})],
        })
        model = type(self.env['account.move'])
        with patch.object(model, '_l10n_ar_request_cae_wsfex') as fex, \
                patch.object(type(self.connection_fex), 'get_active_connection', return_value=self.connection_fex) as conn:
            move.action_post()
        fex.assert_called_once_with(self.connection_fex)
        self.assertEqual(conn.call_args.args[1], 'wsfex')
