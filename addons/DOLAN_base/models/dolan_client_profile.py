from odoo import api, fields, models


class DolanClientProfile(models.Model):
    _name = "dolan.client.profile"
    _description = "Perfil de Módulos por Tipo de Cliente"
    _order = "sequence, id"

    name = fields.Char(string="Nombre del Perfil", required=True)
    code = fields.Selection(
        selection=[
            ("core", "Core Argentina (Facturación ARCA + Contabilidad + IA + Estética)"),
            ("comercio", "Comercio & Gastronomía (Core + PoS Kitchen Display + Código de Barras)"),
            ("industria", "Industria & Manufactura (Core + Taller MRP II + Calidad + Vistas Gantt)"),
            ("servicios", "Servicios, Suscripciones & Alquileres (Core + Abonos + Rental + Wiki/BI)"),
            ("full", "Suite Completa DOLAN (Paridad 100% Demo Web)"),
        ],
        string="Código de Perfil",
        required=True,
        default="full",
    )
    sequence = fields.Integer(default=10)
    description = fields.Text(string="Descripción Funcional")
    module_names = fields.Char(
        string="Módulos Incluidos (CSV)",
        required=True,
        help="Nombres técnicos de los módulos separados por coma.",
    )
    is_applied = fields.Boolean(string="Aplicado", compute="_compute_is_applied")

    @api.depends("module_names")
    def _compute_is_applied(self):
        IrModule = self.env["ir.module.module"].sudo()
        for rec in self:
            names = [m.strip() for m in (rec.module_names or "").split(",") if m.strip()]
            if not names:
                rec.is_applied = False
                continue
            installed_count = IrModule.search_count(
                [("name", "in", names), ("state", "=", "installed")]
            )
            rec.is_applied = installed_count == len(names)

    def action_apply_profile(self):
        """Instala todos los módulos disponibles asociados al perfil seleccionado."""
        self.ensure_one()
        IrModule = self.env["ir.module.module"].sudo()
        names = [m.strip() for m in (self.module_names or "").split(",") if m.strip()]
        to_install = IrModule.search(
            [("name", "in", names), ("state", "in", ["uninstalled", "to install"])]
        )
        if to_install:
            to_install.button_immediate_install()
        # Asegurar que ningún módulo OEEL-1 quede visible como App
        self.env.cr.execute(
            "UPDATE ir_module_module SET application = FALSE WHERE license = 'OEEL-1' AND application = TRUE"
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_hide_enterprise_tiles(self):
        """Limpia en cualquier momento las tarjetas promocionales OEEL-1."""
        self.env.cr.execute(
            "UPDATE ir_module_module SET application = FALSE WHERE license = 'OEEL-1' AND application = TRUE"
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Limpieza CE Completada",
                "message": "Se ocultaron todas las tarjetas promocionales OEEL-1 del menú de Aplicaciones.",
                "type": "success",
                "sticky": False,
            },
        }
