from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAudit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env['dolan.audit.log']
        cls.auditor = new_test_user(cls.env, login='auditor', groups='DOLAN_audit_log.group_audit_viewer')
        cls.clerk = new_test_user(cls.env, login='empleado_audit', groups='base.group_user,base.group_partner_manager')

    def logs(self, record):
        return self.Log.search([('model', '=', record._name), ('res_id', '=', record.id)])

    def test_vat_change_is_logged_with_before_and_after(self):
        partner = self.env['res.partner'].create({'name': 'Proveedor auditado', 'vat': '20111111112'})
        self.assertFalse(self.logs(partner), 'El alta de contactos no se audita por defecto')
        partner.with_user(self.clerk).with_context(dolan_audit_reason='Corrección de CUIT').write({'vat': '20222222223'})
        log = self.logs(partner)
        self.assertEqual(len(log), 1)
        self.assertEqual(log.operation, 'write')
        self.assertEqual(log.user_id, self.clerk)
        self.assertEqual(log.reason, 'Corrección de CUIT')
        self.assertEqual(log.changes[0]['old'], '20111111112')
        self.assertEqual(log.changes[0]['new'], '20222222223')

    def test_unwatched_fields_are_not_logged(self):
        partner = self.env['res.partner'].create({'name': 'Cliente auditado'})
        partner.write({'comment': 'nota', 'phone': '123'})
        self.assertFalse(self.logs(partner))

    def test_price_change_and_product_deletion(self):
        product = self.env['product.template'].create({'name': 'Producto auditado', 'list_price': 10.0})
        product.list_price = 12.5
        self.assertEqual(self.logs(product).changes[0]['new'], 12.5)
        product_id = product.id
        product.unlink()
        deleted = self.Log.search([('model', '=', 'product.template'), ('res_id', '=', product_id), ('operation', '=', 'unlink')])
        self.assertEqual(deleted.res_name, 'Producto auditado')

    def test_bank_account_creation(self):
        partner = self.env['res.partner'].create({'name': 'Titular'})
        bank = self.env['res.partner.bank'].create({'partner_id': partner.id, 'account_number': '0110599520000001234567'})
        self.assertEqual(self.logs(bank).operation, 'create')

    def test_log_is_immutable(self):
        partner = self.env['res.partner'].create({'name': 'X', 'vat': '1'})
        partner.vat = '2'
        log = self.logs(partner)
        with self.assertRaises(AccessError):
            log.write({'reason': 'otro'})
        with self.assertRaises(AccessError):
            log.unlink()
        with self.assertRaises(AccessError):
            self.Log.with_user(self.auditor).create({'model': 'x'})
        self.assertTrue(log.with_user(self.auditor).read(['res_name']))

    def test_rule_can_be_disabled(self):
        self.env.ref('DOLAN_audit_log.rule_partner_tax').active = False
        partner = self.env['res.partner'].create({'name': 'Sin regla', 'vat': '1'})
        partner.vat = '2'
        self.assertFalse(self.logs(partner))

    def test_user_groups_change(self):
        user = new_test_user(self.env, login='nuevo_audit', groups='base.group_user')
        self.assertEqual(self.logs(user).operation, 'create')
        user.write({'group_ids': [(4, self.env.ref('base.group_partner_manager').id)]})
        self.assertIn('write', self.logs(user).mapped('operation'))
