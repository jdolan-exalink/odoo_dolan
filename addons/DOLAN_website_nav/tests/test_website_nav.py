from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestWebsiteNav(HttpCase):

    def test_website_apps_button_goes_to_desktop(self):
        """En el sitio web, el botón de apps lleva al Escritorio y ya no abre la lista de menús."""
        new_test_user(self.env, login='webnav_internal', password='webnav_internal_pw', groups='base.group_user')
        self.authenticate('webnav_internal', 'webnav_internal_pw')
        html = self.url_open('/').text
        self.assertIn('o_dolan_frontend_desktop_btn', html)
        self.assertIn('href="/odoo"', html)
        self.assertNotIn('o_frontend_to_backend_apps_menu', html)

    def test_public_visitor_sees_no_backend_buttons(self):
        html = self.url_open('/').text
        self.assertNotIn('o_dolan_frontend_desktop_btn', html)
