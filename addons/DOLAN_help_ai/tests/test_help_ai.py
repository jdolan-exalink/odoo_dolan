from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpAi(TransactionCase):

    def test_tool_is_offered(self):
        names = [t['function']['name'] for t in self.env['ai.skill'].get_openai_tools_spec()]
        self.assertIn('help_search', names)
        self.assertEqual(names.count('help_search'), 1)

    def test_search_returns_steps_and_link(self):
        result = self.env['ai.skill'].execute_skill_tool('help_search', {'query': 'emitir factura'})
        self.assertEqual(result['status'], 'success')
        first = result['result'][0]
        self.assertEqual(first['link'], '/ayuda/facturacion/emitir-factura')
        self.assertTrue(first['steps'])

    def test_search_respects_permissions(self):
        plain = new_test_user(self.env, login='help_ai_plain', groups='base.group_user')
        result = self.env['ai.skill'].with_user(plain).execute_skill_tool('help_search', '{"query": "emitir factura"}')
        links = [r['link'] for r in result['result']]
        self.assertNotIn('/ayuda/facturacion/emitir-factura', links)

    def test_other_tools_still_work(self):
        result = self.env['ai.skill'].execute_skill_tool('herramienta_que_no_existe', {})
        self.assertEqual(result['status'], 'error')
