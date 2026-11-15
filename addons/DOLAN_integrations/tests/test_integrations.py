from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestIntegrations(TransactionCase):

    def rows(self, kind):
        return self.env['dolan.integration.status'].search([('kind', '=', kind)])

    def test_mail_without_server_is_unconfigured(self):
        self.env['ir.mail_server'].search([]).unlink()
        self.env['dolan.integration.status']._refresh()
        self.assertEqual(self.rows('mail_out').state, 'unconfigured')

    def test_mail_queue_errors(self):
        self.env['mail.mail'].create({'subject': 'x', 'body_html': 'x', 'email_to': 'a@example.com', 'state': 'exception'})
        self.env['dolan.integration.status']._refresh()
        self.assertEqual(self.rows('mail_queue').state, 'error')

    def test_refresh_is_idempotent(self):
        Status = self.env['dolan.integration.status']
        first = Status._refresh()
        second = Status._refresh()
        self.assertEqual(first, second)
        self.assertEqual(Status.search_count([]), second)

    def test_optional_integrations_are_skipped_when_missing(self):
        self.env['dolan.integration.status']._refresh()
        kinds = set(self.env['dolan.integration.status'].search([]).mapped('kind'))
        if 'dolan.whatsapp.account' not in self.env:
            self.assertNotIn('whatsapp', kinds)
        if 'dolan.marketplace.account' not in self.env:
            self.assertNotIn('marketplace', kinds)
