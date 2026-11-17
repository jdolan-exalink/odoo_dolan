"""Carga datos de ejemplo en la COPIA para capturas de la Ayuda (después de help_shots_anonymize.py):
productos con stock, presupuestos y ventas, compras y recepciones, una caja con turnos y movimientos y
pedidos de ausencia. Así cada guía tiene algo real para mostrar.

    docker exec -i <contenedor> python3 /opt/odoo/odoo-server/odoo-bin shell ... -d dolan_help_shots --no-http \
        < scripts/help_shots_seed.py

Se niega con cualquier base que no se llame *help_shots*. Es repetible: lo que ya existe no se duplica.
"""
from datetime import timedelta

from odoo import fields

if 'help_shots' not in env.cr.dbname:  # noqa: F821
    raise SystemExit(f'Me niego: la base {env.cr.dbname} no es una copia para capturas.')  # noqa: F821

E = env(context=dict(env.context, tracking_disable=True, mail_notrack=True, lang='es_AR'), su=True)  # noqa: F821
user = E['res.users'].search([('login', '=', 'ayuda.capturas')], limit=1)
company = user.company_id
E = E(context=dict(E.context, allowed_company_ids=[company.id]))
today = fields.Date.context_today(E['res.users'])
print('empresa', company.id, company.name)


def step(label, fn):
    try:
        with E.cr.savepoint():
            result = fn()
        print('ok   ', label)
        return result
    except Exception as error:  # noqa: BLE001
        print('ERROR', label, '-', str(error).splitlines()[0][:200])
        return None


# --- Productos con stock -------------------------------------------------------------
PRODUCTS = [
    ('Yerba mate 1 kg', 'YER-1000', 4200, 2900, 120),
    ('Aceite de girasol 1,5 L', 'ACE-1500', 3800, 2600, 80),
    ('Harina 000 1 kg', 'HAR-1000', 1100, 700, 200),
    ('Azúcar 1 kg', 'AZU-1000', 1300, 850, 150),
    ('Fideos tirabuzón 500 g', 'FID-0500', 1500, 950, 90),
    ('Arroz largo fino 1 kg', 'ARR-1000', 1900, 1200, 6),
]
Template = E['product.template']
warehouse = E['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
warehouse.name = 'Depósito central'
stock_location = warehouse.lot_stock_id


def make_products():
    products = E['product.product']
    for name, code, price, cost, qty in PRODUCTS:
        tmpl = Template.search([('default_code', '=', code)], limit=1)
        if not tmpl:
            vals = {'name': name, 'default_code': code, 'list_price': price, 'standard_price': cost,
                    'sale_ok': True, 'purchase_ok': True, 'type': 'consu', 'barcode': f'779{abs(hash(code)) % 10**10:010d}'}
            if 'is_storable' in Template._fields:
                vals['is_storable'] = True
            tmpl = Template.create(vals)
            E['stock.quant']._update_available_quantity(tmpl.product_variant_id, stock_location, qty)
        products |= tmpl.product_variant_id
    return products


products = step('productos con stock', make_products) or E['product.product']
customers = E['res.partner'].search([('customer_rank', '>', 0), ('vat', '!=', False), ('parent_id', '=', False),
                                     ('company_id', 'in', (False, company.id))], limit=4)
supplier = E['res.partner'].search([('supplier_rank', '>', 0), ('parent_id', '=', False), ('company_id', 'in', (False, company.id))], limit=1) or customers[-1:]
print('clientes', customers.mapped('name'), 'proveedor', supplier.name)


# --- Ventas ---------------------------------------------------------------------------
def make_sales():
    SO = E['sale.order']
    if SO.search_count([('client_order_ref', '=like', 'AYUDA-%')]):
        return
    for index, partner in enumerate(customers[:3]):
        order = SO.create({
            'partner_id': partner.id,
            'client_order_ref': f'AYUDA-{index + 1}',
            'user_id': user.id or E.uid,
            'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': q}) for p, q in zip(products[index:index + 3], (10, 6, 12))],
        })
        if index == 0:
            order.action_confirm()
            order.picking_ids.action_assign()


if products and customers:
    step('presupuestos y ventas', make_sales)


# --- Compras --------------------------------------------------------------------------
def make_purchases():
    PO = E['purchase.order']
    if PO.search_count([('partner_ref', '=like', 'AYUDA-%')]):
        return
    for index in range(2):
        order = PO.create({
            'partner_id': supplier.id,
            'partner_ref': f'AYUDA-{index + 1}',
            'order_line': [(0, 0, {'product_id': p.id, 'product_qty': q, 'price_unit': p.standard_price})
                           for p, q in zip(products[index * 2:index * 2 + 3], (50, 40, 30))],
        })
        if index == 0:
            order.button_confirm()


if products and supplier and 'purchase.order' in E:
    step('compras', make_purchases)


# --- Caja y Tesorería -----------------------------------------------------------------
def make_cash():
    if 'dolan.cash.box' not in E:
        return
    Box = E['dolan.cash.box']
    box = Box.search([('name', '=', 'Caja mostrador')], limit=1)
    expense = E['account.account'].search([('account_type', '=', 'expense'), ('company_ids', 'in', company.id)], limit=1)
    income = E['account.account'].search([('account_type', 'in', ('income_other', 'income')), ('company_ids', 'in', company.id)], limit=1)
    equity = E['account.account'].search([('account_type', '=', 'equity'), ('company_ids', 'in', company.id)], limit=1) or income
    Reason = E['dolan.cash.reason']
    reasons = {}
    for name, kind, account in (('Gasto de librería', 'out', expense), ('Pago a proveedor en efectivo', 'out', expense),
                                ('Aporte de socio', 'in', equity), ('Retiro de socio', 'out', equity)):
        reasons[name] = Reason.search([('name', '=', name)], limit=1) or Reason.create({'name': name, 'move_type': kind, 'account_id': account.id})
    if not box:
        used = Box.with_context(active_test=False).search([]).mapped('journal_id')
        journal = E['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', company.id), ('id', 'not in', used.ids)], limit=1)
        if not journal:
            journal = E['account.journal'].create({'name': 'Caja mostrador', 'type': 'cash', 'code': 'CJMO', 'company_id': company.id})
        box = Box.create({'name': 'Caja mostrador', 'kind': 'branch', 'journal_id': journal.id, 'user_ids': [(6, 0, user.ids)],
                          'fixed_fund': 50000, 'tolerance': 500,
                          'difference_loss_account_id': expense.id, 'difference_gain_account_id': income.id})
    Session = E['dolan.cash.session'].with_user(user) if user else E['dolan.cash.session']
    if not E['dolan.cash.session'].search_count([('box_id', '=', box.id)]):
        first = Session.create({'box_id': box.id, 'opening_counted': box.ledger_balance})
        move = E['dolan.cash.move'].create({'session_id': first.id, 'kind': 'in', 'reason_id': reasons['Aporte de socio'].id,
                                            'amount': 50000, 'description': 'Fondo para cambio'})
        move.action_post()
        first.action_load_denominations()
        for count in first.count_ids:
            if count.denomination_id.value == 10000:
                count.quantity = 5
        first.action_close()
        second = Session.create({'box_id': box.id, 'opening_counted': box.ledger_balance})
        for reason, amount, text in (('Gasto de librería', 3500, 'Resma y biromes'), ('Pago a proveedor en efectivo', 18000, 'Flete')):
            m = E['dolan.cash.move'].create({'session_id': second.id, 'kind': 'out', 'reason_id': reasons[reason].id,
                                             'amount': amount, 'description': text})
            m.action_post()


step('caja con turnos y movimientos', make_cash)


# --- Ausencias ------------------------------------------------------------------------
EMPLOYEES = [('Lucía Fernández', 'Vendedora'), ('Martín Acosta', 'Depósito'), ('Camila Herrera', 'Cajera')]


def make_leaves():
    if 'hr.leave' not in E:
        return
    Employee = E['hr.employee']
    employees = Employee
    for name, job in EMPLOYEES:
        employees |= Employee.search([('name', '=', name), ('company_id', '=', company.id)], limit=1) or             Employee.create({'name': name, 'job_title': job, 'company_id': company.id})
    # El usuario de las capturas también es empleado, para ver «Mi tiempo» como cualquier empleado.
    own = Employee.search([('user_id', '=', user.id)], limit=1)
    if not own:
        own = Employee.create({'name': user.name, 'user_id': user.id, 'job_title': 'Administración', 'company_id': company.id})
    employees |= own
    if E['hr.leave'].search_count([('private_name', '=like', 'Ayuda:%'), ('employee_id', '=', own.id)]):
        return
    type_model = 'hr.leave.type' if 'hr.leave.type' in E else 'hr.work.entry.type'
    type_field = 'holiday_status_id' if 'holiday_status_id' in E['hr.leave']._fields else 'work_entry_type_id'
    Types = E[type_model]
    # Un tipo que el usuario pueda ver (los que tienen país propio quedan ocultos por regla) y que use asignaciones.
    visible = Types.with_user(user).search([]) if user else Types.search([])
    leave_type = (visible.filtered(lambda t: 'vacacion' in (t.name or '').lower())
                  or visible.filtered(lambda t: getattr(t, 'requires_allocation', False) and 'trabajo' not in (t.name or '').lower())
                  or visible)[:1]
    for index, employee in enumerate(employees):
        if E['hr.leave'].search_count([('private_name', '=like', 'Ayuda:%'), ('employee_id', '=', employee.id)]):
            continue
        allocation = E['hr.leave.allocation'].create({
            'employee_id': employee.id, type_field: leave_type.id, 'number_of_days': 14,
            'date_from': today.replace(month=1, day=1), 'name': f'Vacaciones {today.year}'})
        if allocation.state != 'validate' and hasattr(allocation, 'action_approve'):
            allocation.action_approve()
        day = today + timedelta(days=7 + index * 3)
        E['hr.leave'].create({'employee_id': employee.id, type_field: leave_type.id,
                              'request_date_from': day, 'request_date_to': day + timedelta(days=1 + index),
                              'private_name': f'Ayuda: vacaciones {index + 1}'})


step('pedidos de ausencia', make_leaves)

E.cr.commit()
print('listo')
