# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestIibbPadronAndRetention(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.ar_country = cls.env.ref('base.ar')

        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Padron ARBA Test S.A.',
            'is_company': True,
            'vat': '20055361682', # Valid CUIT
            'country_id': cls.ar_country.id,
        })

    def test_01_iibb_padron_import_and_lookup(self):
        """Valida la importación masiva de padrón ARBA y consulta de alícuotas del contacto."""
        # Archivo simulado mensual ARBA
        padron_csv = (
            "CUIT;Desde;Hasta;AlicPercepcion;AlicRetencion;Grupo\n"
            "20055361682;2026-10-01;2026-10-31;2.50;3.00;1\n"
            "30000000007;2026-10-01;2026-10-31;1.75;2.00;2\n"
        )
        wizard = self.env['dolan.iibb.padron.import.wizard'].create({
            'jurisdiction': 'arba',
            'from_date': date(2026, 10, 1),
            'to_date': date(2026, 10, 31),
            'attachment_filename': 'PadronARBA_102026.csv',
            'attachment_file': base64.b64encode(padron_csv.encode('utf-8')).decode('ascii'),
        })
        wizard.action_import_padron()
        self.assertEqual(wizard.state, 'done')
        self.assertEqual(wizard.records_processed, 2)

        # Consultar alícuotas vigentes para el partner
        percep, ret = self.partner.get_iibb_aliquots('arba', target_date=date(2026, 10, 15))
        self.assertEqual(percep, 2.50)
        self.assertEqual(ret, 3.00)

        # Fecha fuera de vigencia retorna 0.0
        p_out, r_out = self.partner.get_iibb_aliquots('arba', target_date=date(2026, 12, 1))
        self.assertEqual(p_out, 0.0)
        self.assertEqual(r_out, 0.0)

    def test_02_retention_certificate_and_sicore(self):
        """Valida emisión de certificado de retención y generación de registro SICORE/SIRE."""
        cert = self.env['dolan.retention.certificate'].create({
            'company_id': self.company.id,
            'partner_id': self.partner.id,
            'date': date(2026, 10, 20),
            'tax_type': 'ganancias',
            'base_amount': 500000.00,
            'aliquot': 2.00,
            'amount': 10000.00,
            'state': 'confirmed',
        })
        self.assertEqual(cert.state, 'confirmed')
        self.assertEqual(cert.amount, 10000.00)

        # Generar línea SICORE
        line_sicore = cert.generate_sicore_line()
        self.assertTrue(line_sicore.startswith('0120/10/2026'))
        self.assertIn('217', line_sicore) # Código impuesto Ganancias
        self.assertIn('10000,00', line_sicore)
