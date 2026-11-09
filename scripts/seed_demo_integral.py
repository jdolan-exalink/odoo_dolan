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

    # POS catalog fixtures. Keep the products native so they exercise the
    # installed POS and scale modules instead of creating presentation-only data.
    if has_model('product.template') and has_model('pos.config'):
        template_model = env['product.template']
        template_fields = template_model._fields
        kg_uom = env.ref('uom.product_uom_kgm', raise_if_not_found=False)

        def ensure_pos_product(xmlid, name, barcode, price, weighted=False):
            product = find(xmlid)
            if product:
                return product
            vals = {'name': name, 'type': 'consu', 'list_price': price, 'sale_ok': True}
            if 'available_in_pos' in template_fields:
                vals['available_in_pos'] = True
            if 'to_weight' in template_fields:
                vals['to_weight'] = weighted
            if weighted and kg_uom:
                if 'uom_id' in template_fields:
                    vals['uom_id'] = kg_uom.id
                if 'uom_po_id' in template_fields:
                    vals['uom_po_id'] = kg_uom.id
            product = env['product.product'].create(vals)
            if 'barcode' in product._fields:
                product.barcode = barcode
            return bind(xmlid, product)

        pos_unit = ensure_pos_product(
            'pos_unit_product', 'Yerba Mate DEMO — paquete 1 kg',
            '7790000000101', 4200.0,
        )
        pos_weight = ensure_pos_product(
            'pos_weight_product', 'Manzana Roja DEMO — venta por kilogramo',
            '7790000000200', 1850.0, weighted=True,
        )
        results['pos_catalog'] = f'{pos_unit.display_name}; {pos_weight.display_name} (por kg)'

    # ---------------------------------------------------------
    # Accounting demo: posted AR/AP documents and payment states.
    # All amounts, partners and references are fictional. Posting is local;
    # the selected sale journal must not call ARCA and no CAE is generated.
    # ---------------------------------------------------------
    accounting_models = ('account.move', 'account.journal', 'account.account', 'account.tax')
    if all(has_model(model) for model in accounting_models):
        customer = partner
        supplier = find('demo_supplier_ar')
        if not supplier:
            supplier_vals = {
                'name': 'Proveedor Federal de Insumos SA (DEMO FICTICIO)',
                'is_company': True,
                'street': 'Calle de Prueba 567',
                'city': 'Córdoba',
                'email': 'proveedor.ficticio@demo.dolan.invalid',
            }
            ar_country = env.ref('base.ar', raise_if_not_found=False)
            if ar_country:
                supplier_vals['country_id'] = ar_country.id
            if 'supplier_rank' in env['res.partner']._fields:
                supplier_vals['supplier_rank'] = 1
            supplier = bind('demo_supplier_ar', env['res.partner'].create(supplier_vals))

        journals = env['account.journal']
        sale_journal = journals.search([('company_id', '=', company.id), ('type', '=', 'sale')], limit=1)
        purchase_journal = journals.search([('company_id', '=', company.id), ('type', '=', 'purchase')], limit=1)
        bank_journal = journals.search([('company_id', '=', company.id), ('type', '=', 'bank')], limit=1)
        accounts = env['account.account']
        income_account = accounts.search([
            ('company_ids', 'in', company.ids), ('account_type', '=', 'income'),
        ], limit=1)
        expense_account = accounts.search([
            ('company_ids', 'in', company.ids), ('account_type', '=', 'expense'),
        ], limit=1)
        sale_tax = env['account.tax'].search([
            ('company_id', '=', company.id), ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'), ('amount', '=', 21),
        ], limit=1)
        purchase_tax = env['account.tax'].search([
            ('company_id', '=', company.id), ('type_tax_use', '=', 'purchase'),
            ('amount_type', '=', 'percent'), ('amount', '=', 21),
        ], limit=1)
        today = fields.Date.context_today(company)
        move_fields = env['account.move']._fields
        if sale_journal and purchase_journal and income_account and expense_account and sale_tax and purchase_tax:
            if 'l10n_ar_afip_ws' in sale_journal._fields and sale_journal.l10n_ar_afip_ws:
                safe_sale_journal = journals.search([
                    ('company_id', '=', company.id), ('type', '=', 'sale'),
                    ('l10n_ar_afip_ws', '=', False),
                ], limit=1)
                sale_journal = safe_sale_journal

            # Document-type catalog visibility may be limited in the installer
            # shell context; read the public localization catalog with sudo.
            doc_type_model = env['l10n_latam.document.type'].sudo() if has_model('l10n_latam.document.type') else False
            issuer_responsibility = getattr(company, 'l10n_ar_afip_responsibility_type_id', False)
            sale_doc_code = '11' if issuer_responsibility and issuer_responsibility.code == '6' else '6'
            sale_doc = doc_type_model.search([
                ('country_id.code', '=', 'AR'), ('code', '=', sale_doc_code),
            ], limit=1) if doc_type_model is not False else False
            purchase_doc = doc_type_model.search([
                ('country_id.code', '=', 'AR'), ('code', 'in', ['1', '6', '11']),
            ], limit=1) if doc_type_model is not False else False
            credit_doc_code = '13' if sale_doc_code == '11' else '8'
            credit_doc = doc_type_model.search([
                ('country_id.code', '=', 'AR'), ('code', '=', credit_doc_code),
            ], limit=1) if doc_type_model is not False else False

            def ensure_demo_move(xmlid, move_type, journal, account, tax, amount, label,
                                 invoice_date, due_date, target_partner, doc_type=False):
                move = find(xmlid)
                if move:
                    return move
                line_vals = {
                    'name': f'{label} — comprobante de demostración sin validez fiscal',
                    'quantity': 1.0,
                    'price_unit': amount,
                    'account_id': account.id,
                    'tax_ids': [(6, 0, tax.ids)],
                }
                vals = {
                    'move_type': move_type,
                    'partner_id': target_partner.id,
                    'journal_id': journal.id,
                    'invoice_date': invoice_date,
                    'invoice_date_due': due_date,
                    'ref': f'DOLAN-DEMO-{xmlid.upper()}',
                    'invoice_line_ids': [(0, 0, line_vals)],
                }
                if doc_type and 'l10n_latam_document_type_id' in move_fields:
                    vals['l10n_latam_document_type_id'] = doc_type.id
                if move_type in ('in_invoice', 'in_refund') and 'l10n_latam_document_number' in move_fields:
                    demo_numbers = {
                        'ap_paid_bill': '0001-90000001',
                        'ap_overdue_bill': '0001-90000002',
                    }
                    vals['l10n_latam_document_number'] = demo_numbers.get(xmlid, '0001-90000099')
                move = env['account.move'].create(vals)
                # Some localization onchanges can clear the document type
                # while creating a demo move (especially vendor documents).
                # Restore it explicitly before posting so journals requiring
                # Latin American document types never receive an invalid move.
                if doc_type and 'l10n_latam_document_type_id' in move_fields:
                    if move.l10n_latam_document_type_id != doc_type:
                        move.write({'l10n_latam_document_type_id': doc_type.id})
                if move.journal_id.l10n_latam_use_documents and not move.l10n_latam_document_type_id:
                    raise RuntimeError(
                        f'El comprobante demo {xmlid} requiere tipo documental; '
                        f'no se encontró uno para {move.move_type}.'
                    )
                move = bind(xmlid, move)
                move.action_post()
                if getattr(move, 'l10n_ar_afip_auth_code', False):
                    raise RuntimeError('Los comprobantes DEMO no deben tener CAE ni autorización ARCA.')
                return move

            if sale_journal:
                demo_docs = [
                    ('ar_paid_invoice', 120000.0, 'Factura de venta DEMO pagada', today - timedelta(days=10), today - timedelta(days=2)),
                    ('ar_partial_invoice', 60500.0, 'Factura de venta DEMO con pago parcial', today - timedelta(days=8), today + timedelta(days=5)),
                    ('ar_pending_invoice', 85000.0, 'Factura de venta DEMO pendiente', today - timedelta(days=3), today + timedelta(days=15)),
                    ('ar_overdue_invoice', 43000.0, 'Factura de venta DEMO vencida', today - timedelta(days=45), today - timedelta(days=15)),
                ]
                for xmlid, amount, label, issue_date, due_date in demo_docs:
                    ensure_demo_move(xmlid, 'out_invoice', sale_journal, income_account,
                                     sale_tax, amount, label, issue_date, due_date, customer, sale_doc)
                ensure_demo_move('ar_credit_note', 'out_refund', sale_journal, income_account,
                                 sale_tax, 10000.0, 'Nota de crédito de venta DEMO', today - timedelta(days=1), today,
                                 customer, credit_doc)

                if bank_journal and has_model('account.payment.register'):
                    manual_method = bank_journal.inbound_payment_method_line_ids.filtered(
                        lambda method: method.code == 'manual'
                    )[:1]
                    if manual_method:
                        for xmlid, payment_amount in (('ar_paid_invoice', 145200.0), ('ar_partial_invoice', 30000.0)):
                            invoice = find(xmlid)
                            payment_xmlid = xmlid + '_payment'
                            if invoice and not find(payment_xmlid):
                                wizard = env['account.payment.register'].with_context(
                                    active_model='account.move', active_ids=invoice.ids,
                                ).create({
                                    'journal_id': bank_journal.id,
                                    'amount': min(payment_amount, invoice.amount_residual),
                                    'payment_method_line_id': manual_method.id,
                                    'payment_date': today,
                                })
                                payment = wizard._create_payments().ensure_one()
                                bind(payment_xmlid, payment)
                                if payment.move_id:
                                    bind(payment_xmlid + '_entry', payment.move_id)

            if purchase_journal:
                ensure_demo_move('ap_paid_bill', 'in_invoice', purchase_journal, expense_account,
                                 purchase_tax, 60000.0, 'Factura de compra DEMO pagada', today - timedelta(days=12),
                                 today - timedelta(days=3), supplier, purchase_doc)
                ensure_demo_move('ap_pending_bill', 'in_invoice', purchase_journal, expense_account,
                                 purchase_tax, 45000.0, 'Factura de compra DEMO pendiente', today - timedelta(days=2),
                                 today + timedelta(days=20), supplier, purchase_doc)
                ensure_demo_move('ap_overdue_bill', 'in_invoice', purchase_journal, expense_account,
                                 purchase_tax, 32000.0, 'Factura de compra DEMO vencida', today - timedelta(days=35),
                                 today - timedelta(days=5), supplier, purchase_doc)
                if bank_journal and has_model('account.payment.register'):
                    manual_method = bank_journal.outbound_payment_method_line_ids.filtered(
                        lambda method: method.code == 'manual'
                    )[:1]
                    bill = find('ap_paid_bill')
                    if manual_method and bill and not find('ap_paid_bill_payment'):
                        wizard = env['account.payment.register'].with_context(
                            active_model='account.move', active_ids=bill.ids,
                        ).create({
                            'journal_id': bank_journal.id,
                            'amount': bill.amount_residual,
                            'payment_method_line_id': manual_method.id,
                            'payment_date': today,
                        })
                        payment = wizard._create_payments().ensure_one()
                        bind('ap_paid_bill_payment', payment)
                        if payment.move_id:
                            bind('ap_paid_bill_payment_entry', payment.move_id)
            results['accounting_demo'] = 'Facturas de venta pagadas, parciales, pendientes y vencidas; compras y notas de crédito ficticias para reportes IVA.'

            # Add real native check records only when the Argentine check module
            # is installed and the journals already expose the matching methods.
            payment_model = env['account.payment'] if has_model('account.payment') else False
            if payment_model and 'l10n_latam_new_check_ids' in payment_model._fields and bank_journal:
                own_method = bank_journal._get_available_payment_method_lines('outbound').filtered(
                    lambda method: method.code == 'own_checks'
                )[:1]
                if own_method and not find('demo_own_check_payment'):
                    payment = payment_model.create({
                        'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': supplier.id,
                        'journal_id': bank_journal.id, 'payment_method_line_id': own_method.id,
                        'date': today, 'memo': 'DOLAN DEMO — cheque propio ficticio',
                        'l10n_latam_new_check_ids': [(0, 0, {
                            'name': '00990001', 'payment_date': today, 'amount': 90000.0,
                        })],
                    })
                    payment.action_post()
                    bind('demo_own_check_payment', payment)
                    bind('demo_own_check', payment.l10n_latam_new_check_ids.ensure_one())
                cash_journal = journals.search([
                    ('company_id', '=', company.id), ('type', '=', 'cash'),
                ], limit=1)
                third_method = cash_journal._get_available_payment_method_lines('inbound').filtered(
                    lambda method: method.code == 'new_third_party_checks'
                )[:1] if cash_journal else False
                if third_method and not find('demo_third_party_check_payment'):
                    payment = payment_model.create({
                        'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': customer.id,
                        'journal_id': cash_journal.id, 'payment_method_line_id': third_method.id,
                        'date': today, 'memo': 'DOLAN DEMO — cheque de terceros ficticio',
                        'l10n_latam_new_check_ids': [(0, 0, {
                            'name': '00990002', 'payment_date': today + timedelta(days=30), 'amount': 75000.0,
                        })],
                    })
                    payment.action_post()
                    bind('demo_third_party_check_payment', payment)
                    bind('demo_third_party_check', payment.l10n_latam_new_check_ids.ensure_one())
                results['demo_checks'] = 'Cheques propios y de terceros de ejemplo' if own_method or third_method else 'Módulo de cheques instalado sin métodos de pago configurados; se omitieron los cheques.'
        else:
            results['accounting_demo'] = 'Omitido: la empresa no tiene diarios, cuentas contables e IVA 21% para preparar ejemplos seguros.'

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
