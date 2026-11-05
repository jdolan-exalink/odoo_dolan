import logging

_logger = logging.getLogger(__name__)

# Secuencias exactas relevadas con MCP REA en https://Odoo 20
EXALINK_MENU_SEQUENCES = {
    "Discuss": 5,
    "Conversaciones": 5,
    "Calendar": 10,
    "Calendario": 10,
    "To-do": 12,
    "Knowledge": 17,
    "Conocimiento": 17,
    "Contacts": 20,
    "Contactos": 20,
    "CRM": 25,
    "Sales": 30,
    "Ventas": 30,
    "Dashboards": 37,
    "Tableros": 37,
    "Subscriptions": 40,
    "Suscripciones": 40,
    "Rental": 45,
    "Alquiler": 45,
    "AI": 50,
    "IA": 50,
    "Point of Sale": 50,
    "Punto de venta": 50,
    "Kitchen Display": 51,
    "Invoicing": 55,
    "Facturación": 55,
    "Accounting": 60,
    "Contabilidad": 60,
    "Project": 70,
    "Proyecto": 70,
    "Purchase": 135,
    "Compras": 135,
    "Inventory": 140,
    "Inventario": 140,
    "Manufacturing": 145,
    "Fabricación": 145,
    "Shop Floor": 146,
    "Taller": 146,
    "Barcode": 155,
    "Código de barras": 155,
    "Maintenance": 160,
    "Mantenimiento": 160,
    "Employees": 185,
    "Empleados": 185,
    "Fleet": 220,
    "Flota": 220,
    "Expenses": 230,
    "Gastos": 230,
    "Apps": 500,
    "Aplicaciones": 500,
    "Settings": 550,
    "Ajustes": 550,
}


def post_init_hook(env):
    """Ordena los menús raíz igual que la demo web de Odoo 20."""
    _logger.info("DOLAN_theme: Aplicando secuencias de menús raíz estilo Odoo 20 Web...")
    # XML IDs keep both applications stable across languages and renamed labels.
    fixed_sequences = {
        "account.menu_finance": 55,
        "DOLAN_accounting.menu_dolan_accounting_root": 60,
    }
    fixed_menu_ids = set()
    for xmlid, sequence in fixed_sequences.items():
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            fixed_menu_ids.add(menu.id)
            if menu.sequence != sequence:
                menu.sudo().sequence = sequence
    root_menus = env["ir.ui.menu"].sudo().search([("parent_id", "=", False)])
    for menu in root_menus:
        if menu.id in fixed_menu_ids:
            continue
        seq = EXALINK_MENU_SEQUENCES.get(menu.name)
        if seq and menu.sequence != seq:
            menu.sequence = seq
