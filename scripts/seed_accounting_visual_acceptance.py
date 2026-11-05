"""Seed disposable, clearly tagged records for the local E1/E3 UI acceptance.

Run from `odoo-bin shell -d odoo20_dolan` only. This adds fictional check and
bank statement records to the named development database; it never contacts
ARCA or any bank. Every created business record is linked to an XML ID under
`dolan_demo_visual` so reruns are idempotent and the fixtures are identifiable.
"""
from odoo import Command, fields


def seed_visual_acceptance(env):
    if env.cr.dbname != 'odoo20_dolan':
        raise RuntimeError('Visual acceptance fixtures are restricted to odoo20_dolan')

    namespace = 'dolan_demo_visual'

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

    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids))
    company = company.with_env(env)
    partner = env.ref('dolan_demo.partner')
    bank = env['account.journal'].search([
        ('company_id', '=', company.id), ('type', '=', 'bank'),
    ], limit=1)
    bank_charge_account = env['account.account'].search([
        ('company_ids', 'in', company.ids),
        ('account_type', '=', 'expense'),
        ('name', 'ilike', 'Gastos Bancarios'),
    ], limit=1)
    if not (partner and bank and bank_charge_account):
        raise RuntimeError('The accounting demo partner, bank journal and bank-charge expense account are required')

    # Refuse to attach fixture tags to unrelated records or silently replace
    # an existing statement/check workflow in this development database.
    if not find('statement') and env['account.bank.statement.line'].search_count([
        ('journal_id', '=', bank.id),
    ]):
        raise RuntimeError('The bank journal already has statement lines; fixture creation refused')

    today = fields.Date.context_today(company)
    bank = bank.with_company(company)

    def method_line(journal, direction, code, xmlid):
        lines = journal._get_available_payment_method_lines(direction).filtered(
            lambda line: line.code == code
        )
        if lines:
            return lines[0]
        line = env['account.payment.method.line'].create({
            'name': code.replace('_', ' ').title() + ' DEMO',
            'journal_id': journal.id,
            'payment_method_id': env.ref(xmlid).id,
        })
        journal._assign_outstanding_account_to_payment_method_lines(
            direction,
            payment_method_codes=(code,),
            chart_template=company.chart_template,
        )
        return line

    # Native own check, posted as a real Odoo payment against the fictional
    # demo supplier. It is intentionally not reconciled or represented as banked.
    if not find('own_check_payment'):
        own_method = method_line(
            bank, 'outbound', 'own_checks',
            'l10n_latam_check.account_payment_method_own_checks',
        )
        payment = env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id,
            'journal_id': bank.id,
            'payment_method_line_id': own_method.id,
            'date': today,
            'memo': 'DOLAN DEMO - cheque propio ficticio',
            'l10n_latam_new_check_ids': [Command.create({
                'name': '00990001',
                'payment_date': today,
                'amount': 90.00,
            })],
        })
        payment.action_post()
        bind('own_check_payment', payment)
        bind('own_check_entry', payment.move_id)
        bind('own_check', payment.l10n_latam_new_check_ids.ensure_one())

    # Third-party checks held on hand belong to the native cash journal.
    old_third_payment = find('third_party_check_payment')
    if old_third_payment and old_third_payment.journal_id.type != 'cash':
        old_third_payment.action_cancel()
        for old_name, new_name in (
            ('third_party_check_payment', 'superseded_bank_third_party_check_payment'),
            ('third_party_check_entry', 'superseded_bank_third_party_check_entry'),
            ('third_party_check', 'superseded_bank_third_party_check'),
        ):
            external_id = env['ir.model.data'].search([
                ('module', '=', namespace), ('name', '=', old_name),
            ], limit=1)
            if external_id:
                external_id.name = new_name

    cash_journal = env['account.journal'].search([
        ('company_id', '=', company.id),
        ('type', '=', 'cash'),
        ('inbound_payment_method_line_ids.code', '=', 'new_third_party_checks'),
    ], order='id', limit=1)
    if not cash_journal:
        raise RuntimeError('A native cash journal with new_third_party_checks is required')

    # Native third-party check received from the fictional demo customer.
    if not find('third_party_check_payment'):
        third_method = method_line(
            cash_journal, 'inbound', 'new_third_party_checks',
            'l10n_latam_check.account_payment_method_new_third_party_checks',
        )
        payment = env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'journal_id': cash_journal.id,
            'payment_method_line_id': third_method.id,
            'date': today,
            'memo': 'DOLAN DEMO - cheque de terceros ficticio',
            'l10n_latam_new_check_ids': [Command.create({
                'name': '00990002',
                'payment_date': today,
                'amount': 75.00,
            })],
        })
        payment.action_post()
        bind('third_party_check_payment', payment)
        bind('third_party_check_entry', payment.move_id)
        bind('third_party_check', payment.l10n_latam_new_check_ids.ensure_one())

    if not find('statement'):
        demo_payment = env.ref('dolan_demo.payment')
        outstanding = demo_payment.outstanding_account_id
        if not outstanding:
            raise RuntimeError('The demo payment has no outstanding account for exact bank matching')
        # Align the demo journal suspense account with the payment's outstanding
        # account so the acceptance statement can suggest the native payment.
        original_suspense = bank.suspense_account_id
        bind('original_suspense_account', original_suspense)
        bank.suspense_account_id = outstanding

        statement = env['account.bank.statement'].create({
            'name': 'DOLAN DEMO - extracto ficticio de aceptación',
            'journal_id': bank.id,
            'date': today,
            'line_ids': [
                Command.create({
                    'date': today,
                    'payment_ref': 'DOLAN DEMO - acreditación cobro 400',
                    'partner_id': partner.id,
                    'amount': 400.00,
                }),
                Command.create({
                    'date': today,
                    'payment_ref': 'DOLAN DEMO - cargo bancario sin tratamiento fiscal',
                    'amount': -12.34,
                }),
            ],
        })
        bind('statement', statement)
        bind('payment_statement_line', statement.line_ids.sorted('id')[0])
        bind('fee_statement_line', statement.line_ids.sorted('id')[1])
        for index, move in enumerate(statement.line_ids.mapped('move_id'), start=1):
            bind(f'statement_entry_{index}', move)

    env.cr.commit()
    print(
        'VISUAL FIXTURES VERIFIED: own check 90; third-party check 75; '
        'statement exact payment 400 and separate fee -12.34; fictitious data only'
    )


seed_visual_acceptance(env)
