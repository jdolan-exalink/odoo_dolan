from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers.workspace import _company_scoped_domain


@tagged("post_install", "-at_install")
class TestWorkspaceMultiCompany(TransactionCase):
    def test_scoped_domain_uses_only_active_companies(self):
        company_a = self.env.company
        company_b = self.env["res.company"].create({"name": "DOLAN UI Multi A"})
        company_c = self.env["res.company"].create({"name": "DOLAN UI Multi C"})
        self.env.user.sudo().write({"company_ids": [(4, company_b.id), (4, company_c.id)]})
        active_env = self.env(user=self.env.uid, context={
            **self.env.context,
            "allowed_company_ids": [company_a.id, company_b.id],
        })
        domain = _company_scoped_domain(active_env, active_env["account.move"], [("state", "=", "draft")])
        self.assertIn(("company_id", "in", [company_a.id, company_b.id]), domain)
        self.assertNotIn(company_c.id, domain[-1][2])

    def test_shared_records_are_included_only_when_requested(self):
        domain = _company_scoped_domain(self.env, self.env["res.partner"], [], include_shared=True)
        self.assertIn(("company_id", "=", False), domain)
        self.assertIn(("company_id", "in", self.env.companies.ids), domain)

    def test_models_without_company_boundary_are_not_reported_as_scoped(self):
        domain = _company_scoped_domain(self.env, self.env["mail.activity"], [])
        self.assertIsNone(domain)
