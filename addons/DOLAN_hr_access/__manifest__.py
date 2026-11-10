{
    "name": "DOLAN - Acceso de administradores a datos de empleados",
    "version": "20.0.1.0.0",
    "category": "Hidden",
    "summary": "Permite que el rol Administrador abra la lista de usuarios cuando Empleados está instalado",
    "description": """
Odoo 20 da al rol Administrador lectura sobre ``hr.employee`` pero no sobre
``hr.version`` (contratos). La lista de usuarios muestra el puesto de trabajo,
que se calcula desde ``hr.version``, y falla con un error de acceso para los
administradores que no son también Oficiales de Empleados.

Este módulo puente agrega solo lectura de ``hr.version`` al rol Administrador.
Se instala solo cuando están ``hr`` y ``DOLAN_base``.
    """,
    "author": "DOLAN ERP",
    "website": "https://github.com/dolan-erp/odoo20-rea",
    "license": "LGPL-3",
    "depends": ["hr", "DOLAN_base"],
    "data": ["security/ir.access.csv"],
    "installable": True,
    "auto_install": True,
}
