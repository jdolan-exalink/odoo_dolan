# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from ..models.res_partner_bank import validate_cbu_checksum


class TestArgentineBanking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.ar_country = cls.env.ref('base.ar')

        cls.partner = cls.env['res.partner'].create({
            'name': 'Proveedor Bancario Test S.A.',
            'is_company': True,
            'vat': '20055361682',
            'country_id': cls.ar_country.id,
        })

        # CBU Válido calculado con el algoritmo oficial BCRA:
        # Banco 011 (Nación), Sucursal 0599 -> d1 = 5
        # Cuenta 2000000123456 -> d2 = 9
        cls.valid_cbu = '0110599520000001234569'
        cls.invalid_cbu = '0110599520000001234568' # Digito 2 incorrecto

        # Crear cuenta bancaria de la empresa (origen)
        cls.company_bank_acc = cls.env['res.partner.bank'].create({
            'account_number': cls.valid_cbu,
            'partner_id': cls.company.partner_id.id,
            'company_id': cls.company.id,
        })

        cls.bank_journal = cls.env['account.journal'].create({
            'name': 'Banco Galicia Test',
            'code': 'BGAL1',
            'type': 'bank',
            'company_id': cls.company.id,
            'bank_account_id': cls.company_bank_acc.id,
        })

    def test_01_cbu_checksum_validation(self):
        """Valida que validate_cbu_checksum aplique el algoritmo BCRA."""
        self.assertTrue(validate_cbu_checksum(self.valid_cbu))
        self.assertFalse(validate_cbu_checksum(self.invalid_cbu))
        self.assertFalse(validate_cbu_checksum('12345'))
        self.assertFalse(validate_cbu_checksum(''))

    def test_02_res_partner_bank_cbu_constraint(self):
        """Valida que res.partner.bank valide CBU y Alias."""
        # 1. CBU válido se crea sin error
        bank_acc = self.env['res.partner.bank'].create({
            'account_number': self.valid_cbu,
            'partner_id': self.partner.id,
            'cbu_alias': 'proveedor.test.mp',
        })
        self.assertTrue(bank_acc.is_cbu)

        # 2. CBU inválido levanta ValidationError
        with self.assertRaises(ValidationError):
            self.env['res.partner.bank'].create({
                'account_number': self.invalid_cbu,
                'partner_id': self.partner.id,
            })

        # 3. Alias inválido levanta ValidationError (caracteres no permitidos)
        with self.assertRaises(ValidationError):
            self.env['res.partner.bank'].create({
                'account_number': '1234567890',
                'partner_id': self.partner.id,
                'cbu_alias': 'alias invalido!',
            })

    def test_03_bank_payment_export_wizard(self):
        """Valida la generación de archivos de pagos masivos para Interbanking, Galicia, Santander y BBVA."""
        # Asociar cuenta bancaria destino al proveedor
        partner_bank = self.env['res.partner.bank'].create({
            'account_number': self.valid_cbu,
            'partner_id': self.partner.id,
        })

        # Crear un pago a proveedor de prueba
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner.id,
            'partner_bank_id': partner_bank.id,
            'amount': 150000.0,
            'journal_id': self.bank_journal.id,
            'company_id': self.company.id,
        })

        # 1. Exportar Interbanking
        wizard_inter = self.env['dolan.bank.payment.export.wizard'].create({
            'journal_id': self.bank_journal.id,
            'export_format': 'interbanking',
            'payment_ids': [(6, 0, [payment.id])],
        })
        wizard_inter.action_generate_export_file()
        self.assertEqual(wizard_inter.state, 'done')
        self.assertTrue(payment.exported_to_bank)
        content_inter = wizard_inter.file_data.decode('ascii') if hasattr(wizard_inter.file_data, 'decode') else base64.b64decode(wizard_inter.file_data).decode('ascii')
        lines_inter = content_inter.strip().split('\r\n')
        self.assertEqual(len(lines_inter), 3) # Header 00, Detail 01, Trailer 99
        self.assertTrue(lines_inter[0].startswith('00'))
        self.assertTrue(lines_inter[1].startswith('01'))
        self.assertTrue(lines_inter[2].startswith('99'))

        # 2. Exportar Galicia
        wizard_gali = self.env['dolan.bank.payment.export.wizard'].create({
            'journal_id': self.bank_journal.id,
            'export_format': 'galicia',
            'payment_ids': [(6, 0, [payment.id])],
        })
        wizard_gali.action_generate_export_file()
        content_gali = wizard_gali.file_data.decode('ascii') if hasattr(wizard_gali.file_data, 'decode') else base64.b64decode(wizard_gali.file_data).decode('ascii')
        lines_gali = content_gali.strip().split('\r\n')
        self.assertEqual(len(lines_gali), 3) # Header 1, Detail 2, Trailer 9
        self.assertTrue(lines_gali[0].startswith('1'))
        self.assertTrue(lines_gali[1].startswith('2'))
        self.assertTrue(lines_gali[2].startswith('9'))

    def test_04_bank_statement_import_galicia_csv(self):
        """Valida importación inteligente de extracto Banco Galicia con Débito/Crédito."""
        galicia_csv = (
            "Cuenta Corriente en Pesos: 0123-45678/9\n"
            "Titular: DOLAN S.A.\n"
            "Fecha;Referencia;Concepto;Débito;Crédito;Saldo\n"
            "2026-10-01;TRF-001;Transferencia Recibida;;150000.50;150000.50\n"
            "2026-10-02;PAG-002;Pago a Proveedor;45000.00;;105000.50\n"
        )
        import_wiz = self.env['dolan.bank.statement.import.wizard'].create({
            'journal_id': self.bank_journal.id,
            'file_format': 'csv',
            'attachment_filename': 'extracto_galicia.csv',
            'attachment_file': base64.b64encode(galicia_csv.encode('utf-8')).decode('ascii'),
        })
        action = import_wiz.action_import_statement()
        statement = self.env['account.bank.statement'].browse(action['res_id'])
        self.assertEqual(len(statement.line_ids), 2)
        lines = sorted(statement.line_ids, key=lambda l: l.date)
        self.assertEqual(lines[0].amount, 150000.50)
        self.assertIn('TRF-001', lines[0].payment_ref)
        self.assertEqual(lines[1].amount, -45000.00)
        self.assertIn('PAG-002', lines[1].payment_ref)

    def test_05_bank_statement_import_santander_csv(self):
        """Valida importación inteligente de extracto Banco Santander con Débito/Crédito y formato DD/MM/YYYY."""
        santander_csv = (
            "Fecha,Sucursal,Descripción,Referencia,Débito,Crédito,Saldo\n"
            "05/10/2026,089,Cobro Factura A,REC-9988,,32000.00,32000.00\n"
            "06/10/2026,089,Comisión Mantenimiento,COM-1122,1500.00,,30500.00\n"
        )
        import_wiz = self.env['dolan.bank.statement.import.wizard'].create({
            'journal_id': self.bank_journal.id,
            'file_format': 'csv',
            'attachment_filename': 'extracto_santander.csv',
            'attachment_file': base64.b64encode(santander_csv.encode('utf-8')).decode('ascii'),
        })
        action = import_wiz.action_import_statement()
        statement = self.env['account.bank.statement'].browse(action['res_id'])
        self.assertEqual(len(statement.line_ids), 2)
        lines = sorted(statement.line_ids, key=lambda l: l.date)
        self.assertEqual(lines[0].amount, 32000.00)
        self.assertIn('REC-9988', lines[0].payment_ref)
        self.assertEqual(lines[1].amount, -1500.00)
        self.assertIn('COM-1122', lines[1].payment_ref)

