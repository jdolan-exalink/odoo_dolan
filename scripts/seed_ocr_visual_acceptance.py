"""Create a disposable OCR draft and synthetic QR attachment for local UI QA.

Run only in ``odoo20_dolan`` from ``odoo-bin shell``. The draft is unposted,
contains no real CAE and uses an example CUIT; its XML ID makes reruns safe.
"""
import base64
import json

from odoo import fields


def seed_ocr_visual_acceptance(env):
    if env.cr.dbname != 'odoo20_dolan':
        raise RuntimeError('OCR visual fixture is restricted to odoo20_dolan')

    namespace = 'dolan_demo_visual'
    external_ids = env['ir.model.data']

    def find(name):
        return env.ref(f'{namespace}.{name}', raise_if_not_found=False)

    invoice = find('ocr_draft')
    if not invoice:
        company = env.ref('base.main_company')
        purchase_journal = env['account.journal'].search([
            ('company_id', '=', company.id), ('type', '=', 'purchase'),
        ], limit=1)
        if not purchase_journal:
            raise RuntimeError('A native purchase journal is required')
        invoice = env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': purchase_journal.id,
            'partner_id': env.ref('dolan_demo.partner').id,
            'invoice_date': fields.Date.context_today(env.user),
            'ref': 'DOLAN-OCR-UI-FIXTURE',
        })
        external_ids.create({
            'module': namespace,
            'name': 'ocr_draft',
            'model': 'account.move',
            'res_id': invoice.id,
            'noupdate': True,
        })

    if invoice.state != 'draft' or invoice.move_type != 'in_invoice':
        raise RuntimeError('The tagged OCR acceptance record is no longer a draft vendor bill')

    if not find('ocr_attachment'):
        payload = {
            'ver': 1,
            'fecha': fields.Date.to_string(invoice.invoice_date),
            'cuit': '30712345671',
            'ptoVta': 1,
            'tipoCmp': 1,
            'nroCmp': 98765,
            'importe': 1210.0,
            'moneda': 'PES',
            'ctz': 1,
            'tipoCodAut': 'E',
            'codAut': '',
        }
        encoded_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode('utf-8')
        ).decode('ascii').rstrip('=')
        raw_document = (
            'DOLAN DEMO — comprobante sintético de aceptación. Sin validez fiscal.\n'
            f'https://www.afip.gob.ar/fe/qr/?p={encoded_payload}'
        ).encode('utf-8')
        attachment = env['ir.attachment'].create({
            'name': 'DOLAN-DEMO-OCR-SINTETICO.txt',
            'type': 'binary',
            'raw': raw_document,
            'mimetype': 'text/plain',
            'res_model': 'account.move',
            'res_id': invoice.id,
        })
        external_ids.create({
            'module': namespace,
            'name': 'ocr_attachment',
            'model': 'ir.attachment',
            'res_id': attachment.id,
            'noupdate': True,
        })

    env.cr.commit()
    print(f'OCR UI FIXTURE READY: draft vendor bill id={invoice.id}; synthetic QR attachment; no CAE; no ARCA calls')


seed_ocr_visual_acceptance(env)
