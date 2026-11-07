import datetime
import sys
import types
import unittest

if "odoo" not in sys.modules:
    odoo_stub = types.ModuleType("odoo")
    fields_stub = types.SimpleNamespace(
        Date=types.SimpleNamespace(today=lambda: datetime.date(2026, 11, 7)),
        Datetime=types.SimpleNamespace(now=lambda: datetime.datetime(2026, 11, 7, 12, 0, 0)),
    )
    odoo_stub.fields = fields_stub
    sys.modules["odoo"] = odoo_stub

from scripts.seed_demo_integral import seed_demo_integral


class FakeRecord:
    def __init__(self, model_name, values, record_id=1):
        self._name = model_name
        self._values = dict(values)
        self.id = record_id
        self.ids = [record_id]

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        return None

    def __bool__(self):
        return True

    def sudo(self):
        return self

    def with_env(self, env):
        return self

    def write(self, vals):
        self._values.update(vals)
        return True

    def action_start(self):
        self._values["state"] = "active"

    def action_start_preparing(self):
        self._values["state"] = "preparing"

    def action_confirm_reservation(self):
        self._values["state"] = "reserved"

    def action_pickup(self):
        self._values["state"] = "picked_up"

    def action_activate(self):
        self._values["state"] = "active"

    def action_publish(self):
        self._values["is_published"] = True

    def _compute_realtime_metrics(self):
        self._values["computed"] = True


class FakeRecordset:
    def __init__(self, model_name, records):
        self._name = model_name
        self.records = list(records)

    def __bool__(self):
        return bool(self.records)

    def __iter__(self):
        return iter(self.records)

    def __len__(self):
        return len(self.records)

    def write(self, vals):
        for rec in self.records:
            rec.write(vals)
        return True


class FakeModel:
    def __init__(self, name, fields_list=None):
        self.name = name
        self._fields = {f: True for f in (fields_list or ["name", "customer_rank", "supplier_rank"])}
        self.records = []
        self._next_id = 1

    def sudo(self):
        return self

    def browse(self, rec_id):
        for rec in self.records:
            if rec.id == rec_id:
                return rec
        return None

    def search(self, domain, limit=None):
        matched = []
        for rec in self.records:
            ok = True
            for clause in domain:
                if not isinstance(clause, (list, tuple)) or len(clause) != 3:
                    continue
                field, op, val = clause
                rec_val = getattr(rec, field)
                if op == "=" and rec_val != val:
                    ok = False
                    break
            if ok:
                matched.append(rec)
                if limit and len(matched) >= limit:
                    break
        if not matched:
            return FakeRecordset(self.name, [])
        if limit == 1:
            return matched[0]
        return FakeRecordset(self.name, matched)

    def create(self, vals):
        rec = FakeRecord(self.name, vals, self._next_id)
        self._next_id += 1
        self.records.append(rec)
        return rec

    def set_param(self, key, value):
        existing = self.search([("key", "=", key)], limit=1)
        if existing:
            existing.write({"value": value})
            return existing
        return self.create({"key": key, "value": value})

    def get_param(self, key, default=""):
        existing = self.search([("key", "=", key)], limit=1)
        if existing:
            return existing.value
        return default


class FakeCr:
    def __init__(self, dbname):
        self.dbname = dbname
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeRegistry:
    def __init__(self, models):
        self.models = models


class FakeEnv:
    def __init__(self, dbname, enabled_models):
        self.cr = FakeCr(dbname)
        self.context = {}
        self._models = {m: FakeModel(m) for m in enabled_models}
        self.registry = FakeRegistry(self._models)
        self.company = FakeRecord("res.company", {"name": "Empresa Demo SA"}, 1)
        self.user = FakeRecord("res.users", {"name": "Admin"}, 1)
        self._xmlids = {
            "base.main_company": self.company,
            "base.user_admin": self.user,
        }

    def __call__(self, context=None):
        if context is not None:
            self.context = dict(context)
        return self

    def __getitem__(self, item):
        return self._models[item]

    def ref(self, xmlid, raise_if_not_found=True):
        if xmlid in self._xmlids:
            return self._xmlids[xmlid]
        imd = self._models.get("ir.model.data")
        if imd and "." in xmlid:
            module, name = xmlid.split(".", 1)
            rec = imd.search([("module", "=", module), ("name", "=", name)], limit=1)
            if rec:
                return self._models[rec.model].browse(rec.res_id)
        if raise_if_not_found:
            raise ValueError(f"External ID not found: {xmlid}")
        return None


class SeedDemoIntegralTests(unittest.TestCase):
    def test_blocks_production_db_by_default(self):
        env = FakeEnv("odoo_produccion", ["ir.config_parameter", "ir.model.data", "res.partner"])
        with self.assertRaises(RuntimeError):
            seed_demo_integral(env, allow_custom_db=False)

    def test_basico_profile_seeds_idempotently_and_isolates_external_services(self):
        models = [
            "ir.config_parameter",
            "ir.model.data",
            "res.partner",
            "product.product",
            "ir.mail_server",
        ]
        env = FakeEnv("odoo_demo_basico", models)
        env["ir.mail_server"].create({"name": "SMTP Real", "active": True})

        res1 = seed_demo_integral(env, allow_custom_db=True, profile="basico")
        self.assertIn("demo_partner", res1)
        self.assertIn("base_product", res1)
        self.assertEqual(env["ir.config_parameter"].get_param("l10n_ar_fiscal_ws.env_type"), "homologation")
        self.assertEqual(env["ir.config_parameter"].get_param("dolan.demo.enabled"), "true")
        self.assertEqual(env["ir.config_parameter"].get_param("dolan.demo.profile"), "basico")
        self.assertFalse(env["ir.mail_server"].records[0].active)
        self.assertEqual(len(env["res.partner"].records), 1)
        self.assertEqual(len(env["product.product"].records), 1)

        # Second execution (e.g. after backup/restore or re-run) must not duplicate records
        res2 = seed_demo_integral(env, allow_custom_db=True, profile="basico")
        self.assertEqual(len(env["res.partner"].records), 1)
        self.assertEqual(len(env["product.product"].records), 1)
        self.assertEqual(res1["demo_partner"], res2["demo_partner"])

    def test_servicios_comercio_and_completo_profiles(self):
        models = [
            "ir.config_parameter",
            "ir.model.data",
            "res.partner",
            "product.product",
            "product.template",
            "stock.lot",
            "stock.location",
            "dolan.subscription.plan",
            "dolan.subscription",
            "dolan.rental.order",
            "dolan.stock.barcode.session",
            "dolan.quality.point",
            "dolan.quality.alert",
            "dolan.pos.kitchen.ticket",
            "dolan.knowledge.category",
            "dolan.knowledge.article",
            "dolan.bi.dashboard",
            "dolan.bi.kpi.card",
            "dolan.view.planner.item",
        ]
        env = FakeEnv("odoo_demo_completo", models)
        env["product.template"]._fields["is_rental_ok"] = True
        env["product.template"]._fields["rental_price_daily"] = True
        env["product.template"]._fields["rental_price_weekly"] = True
        env["product.template"]._fields["rental_price_monthly"] = True
        env["product.template"]._fields["rental_security_deposit"] = True

        res1 = seed_demo_integral(env, allow_custom_db=True, profile="completo")
        self.assertIn("subscription_plan", res1)
        self.assertIn("subscription_contract", res1)
        self.assertIn("rental_order", res1)
        self.assertIn("barcode_session", res1)
        self.assertIn("quality_point", res1)
        self.assertIn("quality_alert", res1)
        self.assertIn("kds_ticket", res1)
        self.assertIn("knowledge_hierarchy", res1)
        self.assertIn("bi_dashboard", res1)
        self.assertIn("planner_multiview", res1)

        counts_first = {m: len(env[m].records) for m in models}
        seed_demo_integral(env, allow_custom_db=True, profile="completo")
        counts_second = {m: len(env[m].records) for m in models}
        self.assertEqual(counts_first, counts_second)

    def test_multicompany_isolation_rules(self):
        env = FakeEnv("odoo_multicompany", ["res.company", "dolan.subscription.plan"])
        comp_a = env["res.company"].create({"name": "Empresa A SA", "vat": "30711111118"})
        comp_b = env["res.company"].create({"name": "Empresa B SRL", "vat": "30722222229"})

        env["dolan.subscription.plan"].create({"name": "Plan A", "company_id": comp_a.id})
        env["dolan.subscription.plan"].create({"name": "Plan B", "company_id": comp_b.id})

        plans_a = env["dolan.subscription.plan"].search([("company_id", "=", comp_a.id)])
        plans_b = env["dolan.subscription.plan"].search([("company_id", "=", comp_b.id)])
        self.assertEqual(len(plans_a), 1)
        self.assertEqual(plans_a.records[0].name, "Plan A")
        self.assertEqual(len(plans_b), 1)
        self.assertEqual(plans_b.records[0].name, "Plan B")


if __name__ == "__main__":
    unittest.main()
