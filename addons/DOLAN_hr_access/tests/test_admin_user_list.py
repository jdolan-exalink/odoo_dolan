from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAdminUserList(TransactionCase):
    def test_settings_admin_can_read_user_list(self):
        admin = self.env["res.users"].create({
            "name": "Admin sin Empleados",
            "login": "dolan_admin_no_hr@example.com",
            "group_ids": [(6, 0, [self.env.ref("base.group_system").id])],
        })
        self.assertFalse(admin.has_group("hr.group_hr_user"))
        self.env["hr.employee"].create({"name": "Empleado", "user_id": admin.id, "job_title": "Cajero"})
        users = self.env["res.users"].with_user(admin).search([], limit=80)
        rows = users.read(["name", "job_title", "department_id"])
        self.assertTrue(rows)
