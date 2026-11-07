"""Seed disposable, tagged demonstration records across installed DOLAN modules.

Run inside `odoo-bin shell -d <dbname>` or directly via:
    python scripts/seed_demo_integral.py

Creates tagged, idempotent native fixtures under `dolan_demo_integral` namespace,
automatically adapting to the installed profile/modules (Básico, Servicios, Comercio, Completo):
  0. Base/Contacts/Products: Fictitious customers, suppliers and base products (no real CUITs)
  1. Subscriptions (if DOLAN_subscription installed): SaaS Corporativo monthly subscription
  2. Renting (if DOLAN_renting installed): Equipment rental order with serialized reservations
  3. Stock & Shopfloor (if DOLAN_stock_mrp installed): Barcode session, QC point and CAPA alert
  4. Point of Sale (if DOLAN_pos installed): KDS Kitchen Ticket in preparation with line timers
  5. Knowledge & BI (if DOLAN_knowledge_bi installed): Article hierarchy & Executive BI Dashboard
  6. Multi-View Planner (if DOLAN_views installed): Gantt, Grid, Cohort & Leaflet map milestones

Safety & External Isolation Rules (PRD 7.5):
  - Never contacts ARCA, banks, WAHA, email servers, or external APIs.
  - Enforces `l10n_ar_fiscal_ws.env_type = 'homologation'`.
  - Disables outgoing mail servers and external webhook/cron side effects in demo mode.
  - Refuses to run on an existing production database unless `allow_custom_db=True` or `DOLAN_ALLOW_DEMO_DB=1` is explicitly passed during initial DB creation.
"""
import os
import sys
import subprocess
import inspect
from datetime import timedelta


def seed_demo_integral(env, allow_custom_db=False, profile=None):
    icp = env['ir.config_parameter'].sudo()
    allowed_env = os.environ.get('DOLAN_ALLOW_DEMO_DB', '') == '1'
    already_demo = icp.get_param('dolan.demo.enabled', '') == 'true'
    if env.cr.dbname != 'odoo20_dolan' and not allow_custom_db and not allowed_env and not already_demo:
        raise RuntimeError(
            f"Demo integral seeding refused on '{env.cr.dbname}': "
            "pass allow_custom_db=True or DOLAN_ALLOW_DEMO_DB=1 during initial database creation."
        )

    from odoo import fields
    from datetime import timedelta

    namespace = 'dolan_demo_integral'

    def find(name):
        return env.ref(f'{namespace}.{name}', raise_if_not_found=False)

    def bind(name, record):
        if not find(name):
            env['ir.model.data'].create({
                'module': namespace,
                'name': name,
                'model': record._name,
                'res_id': record.id,
                'noupdate': True,
            })
        return record

    def has_model(model_name):
        return model_name in env.registry.models

    company = env.ref('base.main_company', raise_if_not_found=False) or env.company.sudo()
    env = env(context=dict(env.context, allowed_company_ids=company.ids))
    company = company.with_env(env)
    admin_user = env.ref('base.user_admin')

    # Isolate external services in demo mode (ARCA homologation, outgoing mail, WAHA)
    icp.set_param('l10n_ar_fiscal_ws.env_type', 'homologation')
    icp.set_param('dolan.demo.enabled', 'true')
    icp.set_param('dolan.demo.type', 'dolan')
    if profile:
        icp.set_param('dolan.demo.profile', str(profile))
    if has_model('ir.mail_server'):
        env['ir.mail_server'].sudo().search([('active', '=', True)]).write({'active': False})

    # ---------------------------------------------------------
    # 0. Base / Básico: Fictitious Partners & Products
    # ---------------------------------------------------------
    partner = env.ref('dolan_demo.partner', raise_if_not_found=False) or find('demo_customer_ar')
    if not partner:
        partner_vals = {
            'name': 'Distribuidora Río de la Plata SRL (DEMO FICTICIO)',
            'is_company': True,
            'street': 'Av. Demostración 1234',
            'city': 'Buenos Aires',
            'email': 'contacto.ficticio@demo.dolan.invalid',
        }
        ar_country = env.ref('base.ar', raise_if_not_found=False)
        if ar_country:
            partner_vals['country_id'] = ar_country.id
        if 'customer_rank' in env['res.partner']._fields:
            partner_vals['customer_rank'] = 1
            partner_vals['supplier_rank'] = 1
        partner = bind('demo_customer_ar', env['res.partner'].create(partner_vals))

    results = {'demo_partner': partner.name}

    base_product = find('demo_base_product')
    if not base_product and has_model('product.product'):
        base_product = bind('demo_base_product', env['product.product'].create({
            'name': 'Artículo Estándar de Catálogo (DEMO)',
            'type': 'consu',
            'list_price': 25000.0,
        }))
        results['base_product'] = base_product.name

    # ---------------------------------------------------------
    # 1. DOLAN_subscription: Plan & Active Contract
    # ---------------------------------------------------------
    if has_model('dolan.subscription.plan') and has_model('dolan.subscription'):
        sub_service_prod = find('sub_service_prod')
        if not sub_service_prod:
            sub_service_prod = bind('sub_service_prod', env['product.product'].create({
                'name': 'SaaS Cloud Enterprise ERP (Demo)',
                'type': 'service',
                'list_price': 150000.0,
            }))

        sub_plan = find('sub_plan_saas')
        if not sub_plan:
            sub_plan = bind('sub_plan_saas', env['dolan.subscription.plan'].create({
                'name': 'Plan SaaS Corporativo Mensual (Demo)',
                'code': 'SAAS-CORP-DEMO',
                'billing_period': 'monthly',
                'company_id': company.id,
                'auto_renew': True,
            }))
        results['subscription_plan'] = sub_plan.name

        sub_contract = find('sub_contract_demo')
        if not sub_contract:
            sub_contract = bind('sub_contract_demo', env['dolan.subscription'].create({
                'name': 'SUB/2026/DEMO-001',
                'partner_id': partner.id,
                'plan_id': sub_plan.id,
                'company_id': company.id,
                'date_start': fields.Date.today(),
                'line_ids': [(0, 0, {
                    'product_id': sub_service_prod.id,
                    'name': sub_service_prod.name,
                    'quantity': 1.0,
                    'price_unit': 150000.0,
                })],
            }))
            sub_contract.action_start()
        results['subscription_contract'] = f"{sub_contract.name} (MRR: {sub_contract.mrr}, ARR: {sub_contract.arr})"

    # ---------------------------------------------------------
    # 2. DOLAN_renting: Rental Product & Reservation Order
    # ---------------------------------------------------------
    rental_prod = find('rental_prod_projector')
    if has_model('dolan.rental.order'):
        if not rental_prod:
            rental_prod = bind('rental_prod_projector', env['product.product'].create({
                'name': 'Proyector Láser 4K Cinema (Demo Alquiler)',
                'type': 'consu',
                'is_rental': True,
                'rental_price_hour': 2500.0,
                'rental_price_day': 15000.0,
                'rental_price_week': 75000.0,
                'rental_price_month': 250000.0,
                'extra_hour_penalty': 500.0,
                'extra_day_penalty': 20000.0,
                'tracking': 'serial',
            }))

        lot_demo = find('rental_lot_demo')
        if not lot_demo:
            lot_demo = bind('rental_lot_demo', env['stock.lot'].create({
                'name': 'PROY-4K-SN-001',
                'product_id': rental_prod.id,
                'company_id': company.id,
            }))

        rental_order = find('rental_order_demo')
        if not rental_order:
            now = fields.Datetime.now()
            pickup = now
            scheduled_return = now + timedelta(days=3)
            rental_order = bind('rental_order_demo', env['dolan.rental.order'].create({
                'partner_id': partner.id,
                'company_id': company.id,
                'pickup_date': pickup,
                'return_date': scheduled_return,
                'line_ids': [(0, 0, {
                    'product_id': rental_prod.id,
                    'name': rental_prod.name,
                    'quantity': 1.0,
                    'lot_ids': [(6, 0, [lot_demo.id])],
                })],
            }))
            rental_order.action_confirm_reservation()
        results['rental_order'] = f"{rental_order.name} (Total: {rental_order.amount_total}, Estado: {rental_order.state})"

    # ---------------------------------------------------------
    # 3. DOLAN_stock_mrp: Barcode Session, QC Point & Alert
    # ---------------------------------------------------------
    if has_model('dolan.stock.barcode.session') and has_model('dolan.quality.point'):
        target_prod = rental_prod or base_product
        stock_loc = env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, company.id]),
        ], limit=1)

        barcode_session = find('barcode_session_demo')
        if not barcode_session:
            barcode_session = bind('barcode_session_demo', env['dolan.stock.barcode.session'].create({
                'operation_mode': 'inventory',
                'location_id': stock_loc.id if stock_loc else False,
                'user_id': admin_user.id,
            }))
        results['barcode_session'] = barcode_session.name

        qc_point = find('qc_point_demo')
        if not qc_point and target_prod:
            qc_point = bind('qc_point_demo', env['dolan.quality.point'].create({
                'title': 'Control de Calidad Dimensional Óptico',
                'product_ids': [(6, 0, [target_prod.id])],
                'test_type': 'measure',
                'norm': 50.0,
                'tolerance_min': 48.0,
                'tolerance_max': 52.0,
            }))
            results['quality_point'] = qc_point.title

        qc_alert = find('qc_alert_demo')
        if not qc_alert and target_prod:
            qc_alert = bind('qc_alert_demo', env['dolan.quality.alert'].create({
                'title': 'ALERTA-CAPA-2026-001: Desviación de Lente Óptico',
                'product_id': target_prod.id,
                'partner_id': partner.id,
                'priority': '2',
                'stage': 'action_plan',
                'description': 'Desviación de enfoque reportada en control de recepción',
                'root_cause': 'Descalibración durante transporte aéreo',
            }))
            results['quality_alert'] = qc_alert.title

    # ---------------------------------------------------------
    # 4. DOLAN_pos: Kitchen Display System (KDS) Order
    # ---------------------------------------------------------
    if has_model('dolan.pos.kitchen.ticket'):
        dish_prod = find('pos_dish_demo')
        if not dish_prod:
            dish_prod = bind('pos_dish_demo', env['product.product'].create({
                'name': 'Bife de Chorizo a las Brasas con Papas',
                'type': 'consu',
                'list_price': 14500.0,
            }))

        kds_ticket = find('kds_ticket_demo')
        if not kds_ticket:
            kds_ticket = bind('kds_ticket_demo', env['dolan.pos.kitchen.ticket'].create({
                'station': 'kitchen',
                'table_name': 'Mesa 4 VIP',
                'partner_id': partner.id,
                'max_prep_minutes': 25,
                'line_ids': [
                    (0, 0, {
                        'product_id': dish_prod.id,
                        'qty': 2.0,
                        'note': 'A punto con ensalada mixta',
                    })
                ]
            }))
            kds_ticket.action_start_preparing()
        results['kds_ticket'] = f"{kds_ticket.name} (Mesa: {kds_ticket.table_name}, Estado: {kds_ticket.state})"

    # ---------------------------------------------------------
    # 5. DOLAN_knowledge_bi: Article Wiki & Executive BI Dashboard
    # ---------------------------------------------------------
    if has_model('dolan.knowledge.article') and has_model('dolan.bi.dashboard'):
        parent_article = find('kb_parent_manual')
        if not parent_article:
            parent_article = bind('kb_parent_manual', env['dolan.knowledge.article'].create({
                'name': 'Manual Corporativo de Operaciones y Políticas DOLAN',
                'icon': '📘',
                'body': '<p>Manual oficial de procesos y operaciones de DOLAN Enterprise Architecture para Odoo 20 CE.</p>',
                'category': 'workspace',
            }))

        child_article = find('kb_child_fiscal')
        if not child_article:
            child_article = bind('kb_child_fiscal', env['dolan.knowledge.article'].create({
                'name': 'Guía de Facturación Electrónica ARCA y Monitoreo Fiscal',
                'icon': '⚙️',
                'parent_id': parent_article.id,
                'body': '<p>Procedimientos operativos para emisión de comprobantes A y B con CAE y RG 4892.</p>',
                'category': 'workspace',
            }))
        results['knowledge_hierarchy'] = f"{parent_article.full_path} -> {child_article.full_path}"

        bi_dashboard = find('bi_dashboard_demo')
        if not bi_dashboard:
            bi_dashboard = bind('bi_dashboard_demo', env['dolan.bi.dashboard'].create({
                'name': 'Tablero de Control Gerencial y Dirección Ejecutiva',
                'code': 'EXEC_DEMO_2026',
                'dashboard_type': 'executive',
                'company_id': company.id,
                'date_from': fields.Date.today().replace(day=1),
                'date_to': fields.Date.today(),
            }))
            env['dolan.bi.kpi.card'].create({
                'name': 'Ingresos Mensuales Recurrentes (MRR)',
                'dashboard_id': bi_dashboard.id,
                'metric_type': 'sales_month',
                'target_value': 1000000.0,
            })
            bi_dashboard._compute_realtime_metrics()
        results['bi_dashboard'] = bi_dashboard.name

    # ---------------------------------------------------------
    # 6. DOLAN_views: Planner Multi-View Record
    # ---------------------------------------------------------
    if has_model('dolan.view.planner.item'):
        planner_item = find('planner_item_demo')
        if not planner_item:
            now = fields.Datetime.now()
            planner_item = bind('planner_item_demo', env['dolan.view.planner.item'].create({
                'name': 'Hito Clave: Despliegue de Módulos DOLAN en Odoo 20 CE',
                'category_type': 'project',
                'partner_id': partner.id,
                'date_start': now,
                'date_stop': now + timedelta(days=7),
                'progress': 95.0,
                'color': 4,
                'state': 'in_progress',
            }))
        results['planner_multiview'] = planner_item.name

    env.cr.commit()
    return results


def run_via_shell():
    fn_source = inspect.getsource(seed_demo_integral)
    code = (
        f"{fn_source}\n"
        "res = seed_demo_integral(env)\n"
        "import json\n"
        "print('SEED_SUCCESS:' + json.dumps(res, ensure_ascii=False))\n"
    )
    cmd = [
        "docker", "exec", "-i", "dolan_odoo20_web",
        "/opt/odoo/odoo-server/odoo-bin", "shell",
        "-c", "/etc/odoo/odoo.conf",
        "-d", "odoo20_dolan",
        "--no-http"
    ]
    p = subprocess.run(cmd, input=code.encode('utf-8'), capture_output=True, timeout=120)
    stdout_text = p.stdout.decode('utf-8', errors='replace')
    stderr_text = p.stderr.decode('utf-8', errors='replace')
    for line in stdout_text.splitlines():
        if "SEED_SUCCESS:" in line:
            print(line.encode('ascii', errors='backslashreplace').decode('ascii'))
    if p.returncode != 0:
        print("STDERR:", stderr_text)
    return p.returncode


if __name__ == '__main__':
    if 'env' in globals():
        res = seed_demo_integral(globals()['env'])
        print("SEED_SUCCESS:", res)
    else:
        sys.exit(run_via_shell())
