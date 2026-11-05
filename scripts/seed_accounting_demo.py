"""Execute inside `odoo-bin shell` against the disposable odoo20_dolan DB.

Creates tagged, idempotent native demo records. No ARCA calls or fabricated CAE.
Public CUIT examples from ARCA QR documentation are used exclusively as fixtures.
"""
from odoo import Command, fields


def seed(env):
    if env.cr.dbname != 'odoo20_dolan':
        raise RuntimeError('This seed is restricted to odoo20_dolan')
    namespace = 'dolan_demo'

    def find(name):
        return env.ref(namespace + '.' + name, raise_if_not_found=False)

    def bind(name, record):
        env['ir.model.data'].create({
            'module': namespace, 'name': name, 'model': record._name,
            'res_id': record.id, 'noupdate': True,
        })
        return record

    # Refuse to repurpose a database containing untagged accounting transactions.
    tagged = env['ir.model.data'].search([('module', '=', namespace), ('model', '=', 'account.move')]).mapped('res_id')
    if env['account.move'].search_count([('id', 'not in', tagged)]):
        raise RuntimeError('Untagged accounting entries exist; seed refused without changing data')
    company = env.ref('base.main_company')
    if company.chart_template != 'ar_ri':
        raise RuntimeError('The demo requires the native ar_ri chart')
    env = env(context=dict(env.context, allowed_company_ids=company.ids))
    company = company.with_env(env)
    company.write({'name': 'DOLAN Demo (datos ficticios)', 'vat': '30000000007'})
    partner = find('partner')
    if not partner:
        partner = bind('partner', env['res.partner'].create({
            'name': 'Cliente y proveedor DEMO (datos ficticios)',
            'is_company': True, 'country_id': env.ref('base.ar').id,
            'vat': '20000000001',
            'l10n_ar_afip_responsibility_type_id': env.ref('l10n_ar.res_IVARI').id,
            'customer_rank': 1, 'supplier_rank': 1,
        }))
    journals = env['account.journal']
    sale = journals.search([
        ('company_id', '=', company.id), ('type', '=', 'sale'),
        ('l10n_ar_afip_pos_system', '=', 'II_IM'),
    ], limit=1)
    purchase = journals.search([('company_id', '=', company.id), ('type', '=', 'purchase')], limit=1)
    bank = journals.search([('company_id', '=', company.id), ('type', '=', 'bank')], limit=1)
    if not (sale and purchase and bank):
        raise RuntimeError('Native preprinted, purchase and bank journals are required')
    sale._compute_l10n_ar_afip_ws()
    if sale.l10n_ar_afip_ws:
        raise RuntimeError('The demo must never use an electronic journal')
    accounts = env['account.account']
    income = accounts.search([('company_ids', 'in', company.ids), ('account_type', '=', 'income')], limit=1)
    expense = accounts.search([('company_ids', 'in', company.ids), ('account_type', '=', 'expense')], limit=1)
    document = env['l10n_latam.document.type'].search([('country_id.code', '=', 'AR'), ('code', '=', '1')], limit=1)
    today = fields.Date.context_today(company)
    for name, move_type, journal, account, amount, tax_use in (
        ('invoice', 'out_invoice', sale, income, 1000, 'sale'),
        ('bill', 'in_invoice', purchase, expense, 500, 'purchase'),
    ):
        move = find(name)
        if move:
            continue
        tax = env['account.tax'].search([
            ('company_id', '=', company.id), ('type_tax_use', '=', tax_use),
            ('amount_type', '=', 'percent'), ('amount', '=', 21),
        ], limit=1)
        if not (account and tax and document):
            raise RuntimeError('Native accounts, invoice A document and VAT21 are required')
        vals = {
            'move_type': move_type, 'partner_id': partner.id, 'journal_id': journal.id,
            'invoice_date': today, 'invoice_date_due': today,
            'l10n_latam_document_type_id': document.id,
            'ref': 'DOLAN-DEMO-' + name.upper(),
            'invoice_line_ids': [Command.create({
                'name': 'Servicio DEMO — comprobante de desarrollo sin validez fiscal',
                'quantity': 1, 'price_unit': amount, 'account_id': account.id,
                'tax_ids': [Command.set(tax.ids)],
            })],
        }
        if move_type == 'in_invoice':
            vals['l10n_latam_document_number'] = '0001-00000001'
        move = bind(name, env['account.move'].create(vals))
        move.action_post()
        if move.l10n_ar_afip_auth_code:
            raise RuntimeError('A demo document must not contain a generated fiscal authorization')
    invoice = find('invoice')
    if not find('payment'):
        pending = find('outstanding') or bind('outstanding', accounts.create({
            'name': 'Cobros pendientes DEMO', 'code': 'DOLANDEMO01',
            'account_type': 'asset_current', 'reconcile': True,
            'company_ids': [Command.set(company.ids)],
        }))
        method = bank.inbound_payment_method_line_ids.filtered(lambda line: line.code == 'manual')[:1]
        if not method:
            raise RuntimeError('Manual inbound payment method required')
        method.payment_account_id = pending
        wizard = env['account.payment.register'].with_context(active_model='account.move', active_ids=invoice.ids).create({
            'journal_id': bank.id, 'amount': 400, 'payment_method_line_id': method.id,
        })
        payment = bind('payment', wizard._create_payments().ensure_one())
        bind('payment_entry', payment.move_id)
    invoice.invalidate_recordset()
    bill = find('bill')
    assert invoice.amount_total == 1210 and invoice.amount_residual == 810
    assert bill.amount_total == 605 and bill.amount_residual == 605
    assert find('payment').move_id.state == 'posted'
    env.cr.commit()
    print('DEMO VERIFIED: invoice1210 / residual810; bill605; payment400; no CAE or external calls')


seed(env)
