from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..hooks import post_init_hook


@tagged('post_install', '-at_install')
class TestMenuOrder(TransactionCase):
    def test_invoicing_sequence_ignores_label_and_language(self):
        invoicing = self.env.ref('account.menu_finance')
        invoicing.write({'name': 'Etiqueta personalizada', 'sequence': 800})
        post_init_hook(self.env(context=dict(self.env.context, lang='en_US')))
        self.assertEqual(invoicing.sequence, 55)

    def test_accounting_sequence_when_module_available(self):
        accounting = self.env.ref(
            'DOLAN_accounting.menu_dolan_accounting_root', raise_if_not_found=False,
        )
        if not accounting:
            self.skipTest('DOLAN_accounting is optional for the theme')
        accounting.write({'name': 'Otra etiqueta', 'sequence': 801})
        post_init_hook(self.env)
        self.assertEqual(accounting.sequence, 60)
