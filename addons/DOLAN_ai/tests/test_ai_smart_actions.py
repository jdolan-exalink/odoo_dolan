# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAiSmartActions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({
            'name': 'Smart action test agent',
            'is_system_agent': True,
        })

    def _session_for(self, record):
        return self.env['ai.session'].create({
            'name': 'Smart action test',
            'agent_id': self.agent.id,
            'request_user_id': self.env.uid,
            'res_model': record._name,
            'res_id': record.id,
        })

    def test_chatter_summary_context_is_access_checked_and_plain_text(self):
        partner = self.env['res.partner'].create({'name': 'Contacto para resumen IA'})
        self.env['mail.message'].create({
            'model': partner._name,
            'res_id': partner.id,
            'message_type': 'comment',
            'subtype_id': self.env.ref('mail.mt_comment').id,
            'author_id': self.env.user.partner_id.id,
            'body': '<p>Confirmó recepción y solicitó el detalle.</p>',
        })
        session = self._session_for(partner)

        context = session._build_smart_action_context('summarize_chatter')

        self.assertIn('Confirmó recepción y solicitó el detalle.', context)
        self.assertNotIn('<p>', context)
        self.assertIn('no confiable', context)
        self.assertEqual(
            self.env['ai.session'].get_available_smart_actions(partner._name, partner.id),
            ['summarize_chatter'],
        )

    def test_smart_action_rejects_unknown_action_and_missing_chatter(self):
        partner = self.env['res.partner'].create({'name': 'Contacto sin mensajes'})
        session = self._session_for(partner)

        with self.assertRaises(UserError):
            session._build_smart_action_context('publish_invoice')
        with self.assertRaises(UserError):
            session._build_smart_action_context('summarize_chatter')

    def test_collection_action_rejects_non_invoice_records(self):
        partner = self.env['res.partner'].create({'name': 'No es una factura'})
        session = self._session_for(partner)

        with self.assertRaisesRegex(UserError, 'facturas de cliente'):
            session._build_smart_action_context('draft_collection')

    def test_available_actions_are_limited_to_records_with_chatter_or_open_balance(self):
        partner = self.env['res.partner'].create({'name': 'Contacto sin contexto asistido'})
        session_model = self.env['ai.session']
        self.assertEqual(session_model.get_available_smart_actions(partner._name, partner.id), [])
        self.assertEqual(session_model.get_available_smart_actions('res.partner', 'not-an-id'), [])

    def test_collection_draft_contains_only_invoice_summary_and_never_sends_mail(self):
        if 'account.move' not in self.env:
            self.skipTest('El módulo contable no está instalado en esta base.')
        company = self.env.company
        argentina = self.env.ref('base.ar')
        company.partner_id.with_context(no_vat_validation=True).write({
            'country_id': argentina.id,
            'vat': '30712345671',
        })
        company.write({'account_fiscal_country_id': argentina.id})
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', company.id),
        ], limit=1)
        if journal and 'l10n_latam_use_documents' in journal._fields:
            journal = journal.copy({
                'name': 'AI Test Sales Journal',
                'code': 'AITS',
                'l10n_latam_use_documents': True,
                'l10n_ar_is_pos': True,
                'l10n_ar_afip_pos_number': 99,
                'l10n_ar_afip_pos_system': 'II_IM',
            })
        vat = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('company_id', '=', company.id),
            ('amount', '=', 21),
        ], limit=1)
        income = self.env['account.account'].search([
            ('account_type', 'in', ('income', 'income_other')),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if 'l10n_latam.document.type' not in self.env or 'l10n_ar.afip.responsibility.type' not in self.env:
            self.skipTest('La localización argentina no está instalada en esta base.')
        document_type = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'AR'), ('internal_type', '=', 'invoice'),
            ('code', '=', '1'), ('l10n_ar_letter', '=', 'A'),
        ], limit=1)
        responsibility = self.env['l10n_ar.afip.responsibility.type'].search([
            ('code', '=', '1'),
        ], limit=1)
        if not journal or not income or not vat or not document_type or not responsibility:
            self.skipTest('La compañía no tiene diario de ventas o cuenta de ingresos configurados.')
        company.write({'l10n_ar_afip_responsibility_type_id': responsibility.id})
        customer = self.env['res.partner'].with_context(no_vat_validation=True).create({
            'name': 'Cliente de cobranza IA',
            'customer_rank': 1,
            'country_id': argentina.id,
            'vat': '30712345672',
            'l10n_ar_afip_responsibility_type_id': responsibility.id,
        })
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': journal.id,
            'partner_id': customer.id,
            'invoice_date': '2026-10-30',
            'l10n_latam_document_type_id': document_type.id,
            'l10n_ar_afip_responsibility_type_id': responsibility.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio de prueba',
                'quantity': 1,
                'price_unit': 1250,
                'account_id': income.id,
                'tax_ids': [(6, 0, vat.ids)],
            })],
        })
        invoice.action_post()
        session = self._session_for(invoice)

        context = session._build_smart_action_context('draft_collection')

        self.assertIn('Cliente de cobranza IA', context)
        self.assertIn(invoice.name, context)
        self.assertIn(f'{invoice.amount_residual:.2f}', context)
        self.assertIn('No envíes ni publiques', context)
        self.assertEqual(invoice.state, 'posted')
        self.assertFalse(invoice.message_ids.filtered(lambda message: message.message_type == 'email'))
        self.assertEqual(
            self.env['ai.session'].get_available_smart_actions(invoice._name, invoice.id),
            ['draft_collection'],
        )

    def test_action_context_is_used_for_one_request_only(self):
        partner = self.env['res.partner'].create({'name': 'Contexto efímero'})
        self.env['mail.message'].create({
            'model': partner._name,
            'res_id': partner.id,
            'message_type': 'comment',
            'subtype_id': self.env.ref('mail.mt_comment').id,
            'author_id': self.env.user.partner_id.id,
            'body': '<p>El cliente confirmó el envío de documentación.</p>',
        })
        session = self._session_for(partner)
        with patch(
            'odoo.addons.DOLAN_ai.models.ai_oauth_provider.DolanAiProvider.generate_completion',
            return_value={
                'content': 'Resumen preparado.', 'tool_calls': [], 'provider': 'test',
                'model': 'test-model', 'raw': {},
            },
        ) as generate_completion:
            result = session.send_user_message(
                'Resumí el Chatter.', smart_action='summarize_chatter',
            )

        messages = generate_completion.call_args.kwargs['messages']
        self.assertIn('El cliente confirmó el envío de documentación.', messages[0]['content'])
        self.assertEqual(result['reply'], 'Resumen preparado.')
        self.assertNotIn('El cliente confirmó el envío de documentación.', session.event_ids.filtered(
            lambda event: event.role == 'user'
        ).content)
