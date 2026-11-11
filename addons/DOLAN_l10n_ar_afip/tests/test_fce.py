# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
import xml.etree.ElementTree as ET
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .test_authorization_safety import TestAuthorizationSafety

CBU = '2850590940090418135201'


def _local(node):
    return node.tag.split('}')[-1]


@tagged('post_install', '-at_install')
class TestDolanFce(AccountTestInvoicingCommon):
    _posted_wsfe_invoice = TestAuthorizationSafety._posted_wsfe_invoice

    def _build(self, invoice, conn):
        conditions = ET.fromstring('''<ResultGet><CondicionIvaReceptor><Id>1</Id>
            <Desc>IVA Responsable Inscripto</Desc><Cmp_Clase>A</Cmp_Clase></CondicionIvaReceptor></ResultGet>''')
        with patch.object(type(conn), '_call_wsfe_query', return_value=conditions):
            return invoice._l10n_ar_build_wsfe_request_xml(conn)

    def _fce_doc_type(self, code):
        doc_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('code', '=', code)], limit=1)
        self.assertTrue(doc_type)
        return doc_type

    def _company_cbu(self):
        company = self.company_data['company']
        return self.env['res.partner.bank'].create({'account_number': CBU, 'partner_id': company.partner_id.id})

    def _posted_fce(self, with_cbu=True):
        invoice, conn = self._posted_wsfe_invoice()
        if with_cbu:
            self._company_cbu()
        invoice.button_draft()
        invoice.write({
            'l10n_latam_document_type_id': self._fce_doc_type('201').id,
            'invoice_date_due': fields.Date.add(invoice.invoice_date, days=30),
        })
        invoice.action_post()
        return invoice, conn

    def _fake_conn(self, responses):
        """Conexión WSFECRED real con el POST reemplazado por respuestas fijas."""
        conn = self.env['l10n_ar.afipws.connection'].create({
            'company_id': self.company_data['company'].id, 'l10n_ar_afip_ws': 'wsfecred', 'type': 'testing',
            'token': 'TOKEN', 'sign': 'SIGN',
        })
        sent = []

        def fake_post(this, envelope, service, soap_action, method, timeout=25):
            sent.append((method, envelope.decode() if isinstance(envelope, bytes) else envelope))
            return ET.fromstring(responses.pop(0))

        conn_model = type(self.env['l10n_ar.afipws.connection'])
        return conn, sent, [
            patch.object(conn_model, '_ws_post_envelope', fake_post),
            patch.object(conn_model, 'get_active_connection', lambda *a, **k: conn),
        ]

    # ------------------------------------------------------------------
    def test_01_fce_invoice_sends_optionals_and_due_date(self):
        invoice, conn = self._posted_fce()
        self.assertTrue(invoice.dolan_fce_is_fce)
        self.assertEqual(invoice.dolan_fce_state, 'pending')
        root = ET.fromstring(self._build(invoice, conn).encode())
        detail = next(n for n in root.iter() if _local(n) == 'FECAEDetRequest')
        tags = [_local(n) for n in detail]
        self.assertIn('FchVtoPago', tags)
        self.assertLess(tags.index('FchVtoPago'), tags.index('MonId'))
        optionals = {
            next(c.text for c in o if _local(c) == 'Id'): next(c.text for c in o if _local(c) == 'Valor')
            for o in root.iter() if _local(o) == 'Opcional'
        }
        self.assertEqual(optionals, {'2101': CBU, '27': 'SCA'})
        self.company_data['company'].l10n_ar_fce_transmission_type = 'ADC'
        root = ET.fromstring(self._build(invoice, conn).encode())
        self.assertIn('ADC', [n.text for n in root.iter() if _local(n) == 'Valor'])

    def test_02_fce_without_cbu_is_blocked(self):
        invoice, conn = self._posted_fce(with_cbu=False)
        with self.assertRaisesRegex(UserError, 'CBU'):
            self._build(invoice, conn)

    def test_03_common_invoice_has_no_optionals(self):
        invoice, conn = self._posted_wsfe_invoice()
        xml = self._build(invoice, conn)
        self.assertNotIn('Opcional', xml)
        self.assertFalse(invoice.dolan_fce_state)

    def test_04_suggest_and_switch_to_fce(self):
        invoice, __ = self._posted_wsfe_invoice()
        invoice.button_draft()
        self._company_cbu()
        self.company_data['company'].dolan_fce_is_mipyme = True
        partner = invoice.partner_id.commercial_partner_id
        partner.write({'dolan_fce_obligated': True, 'dolan_fce_min_amount': invoice.amount_total + 1})
        self.assertFalse(invoice.dolan_fce_suggested, 'Debajo del monto mínimo no corresponde FCE')
        partner.dolan_fce_min_amount = invoice.amount_total
        self.assertTrue(invoice.dolan_fce_suggested)
        invoice.action_dolan_fce_switch()
        self.assertEqual(invoice.l10n_latam_document_type_id.code, '201')
        self.assertEqual(invoice.l10n_ar_fce_cbu_id.account_number, CBU)
        self.assertFalse(invoice.dolan_fce_suggested)

    def test_05_partner_obligation_check(self):
        invoice, __ = self._posted_wsfe_invoice()
        partner = invoice.partner_id
        response = '''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>
            <ns2:consultarMontoObligadoRecepcionResponse xmlns:ns2="http://ar.gob.afip.wsfecred/FECredService/">
            <consultarMontoObligadoRecepcionReturn><obligado>S</obligado><montoDesde>3958316.00</montoDesde>
            </consultarMontoObligadoRecepcionReturn></ns2:consultarMontoObligadoRecepcionResponse></soap:Body></soap:Envelope>'''
        __, sent, patches = self._fake_conn([response])
        with patches[0], patches[1]:
            partner.action_dolan_fce_check()
        self.assertTrue(partner.dolan_fce_obligated)
        self.assertAlmostEqual(partner.dolan_fce_min_amount, 3958316.0)
        self.assertEqual(partner.dolan_fce_check_date, fields.Date.context_today(partner))
        method, envelope = sent[0]
        self.assertEqual(method, 'consultarMontoObligadoRecepcion')
        self.assertIn('<cuitConsultada>30712345672</cuitConsultada>', envelope)
        self.assertIn('<token>TOKEN</token>', envelope)

    def test_06_refresh_state_and_errors(self):
        invoice, __ = self._posted_fce()
        ok = '''<Envelope><Body><consultarCtaCteResponse><ctaCte><codCtaCte>777</codCtaCte>
            <estado><estado>Aceptada</estado></estado><saldo>1210.00</saldo></ctaCte>
            </consultarCtaCteResponse></Body></Envelope>'''
        error = '''<Envelope><Body><consultarCtaCteResponse><arrayErrores><codigoDescripcion>
            <codigo>1500</codigo><descripcion>Comprobante inexistente</descripcion></codigoDescripcion>
            </arrayErrores></consultarCtaCteResponse></Body></Envelope>'''
        __, sent, patches = self._fake_conn([ok, error])
        with patches[0], patches[1]:
            invoice.action_dolan_fce_refresh()
            self.assertEqual(invoice.dolan_fce_state, 'accepted')
            self.assertEqual(invoice.dolan_fce_ctacte_code, '777')
            self.assertAlmostEqual(invoice.dolan_fce_balance, 1210.0)
            self.assertIn('<codTipoCmp>201</codTipoCmp>', sent[0][1])
            self.assertIn('<CUITEmisor>30712345671</CUITEmisor>', sent[0][1])
            with self.assertRaisesRegex(UserError, 'Comprobante inexistente'):
                invoice.action_dolan_fce_refresh()

    def test_07_received_fce_accept_and_reject(self):
        invoice, __ = self._posted_wsfe_invoice()
        vendor = invoice.partner_id
        bills = self.env['account.move']
        for number in ('00002-00000010', '00002-00000011'):
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': vendor.id,
                'invoice_date': invoice.invoice_date,
                'invoice_date_due': fields.Date.add(invoice.invoice_date, days=30),
                'l10n_latam_document_type_id': self._fce_doc_type('201').id,
                'l10n_latam_document_number': number,
                'invoice_line_ids': [Command.create({
                    'name': 'Servicio', 'quantity': 1, 'price_unit': 1000.0, 'tax_ids': [Command.clear()],
                    'account_id': self.company_data['default_account_expense'].id,
                })],
            })
            bill.action_post()
            bills |= bill
        accept_bill, reject_bill = bills
        self.assertEqual(accept_bill.dolan_fce_state, 'pending')
        ok = '<Envelope><Body><respuesta><resultado>A</resultado></respuesta></Body></Envelope>'
        __, sent, patches = self._fake_conn([ok, ok])
        with patches[0], patches[1]:
            accept_bill.action_dolan_fce_accept()
            wizard = self.env['dolan.fce.reject.wizard'].create({
                'move_ids': [Command.set(reject_bill.ids)], 'reason': '1', 'justification': 'No llegó la mercadería',
            })
            wizard.action_confirm()
        self.assertEqual(accept_bill.dolan_fce_state, 'accepted')
        self.assertIn('<saldoAceptado>1000.00</saldoAceptado>', sent[0][1])
        self.assertIn('<CUITEmisor>30712345672</CUITEmisor>', sent[0][1])
        self.assertIn('<nroCmp>10</nroCmp>', sent[0][1])
        self.assertEqual(reject_bill.dolan_fce_state, 'rejected')
        self.assertIn('<codMotivo>1</codMotivo>', sent[1][1])
        self.assertIn('No llegó la mercadería', reject_bill.dolan_fce_rejection_reason)
        with self.assertRaises(UserError):
            invoice.action_dolan_fce_accept()
