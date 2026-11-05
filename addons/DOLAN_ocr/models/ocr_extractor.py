# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
import io
import json
import logging
import re
import urllib.parse

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

AFIP_QR_REGEX = re.compile(
    r'https?://(?:www\.)?(?:afip|arca)\.gob\.ar/fe/qr/\?p=([A-Za-z0-9+/=%_-]+)',
    re.IGNORECASE,
)

AFIP_TIPO_CMP_MAP = {
    1: 'FA-A',
    2: 'ND-A',
    3: 'NC-A',
    6: 'FA-B',
    7: 'ND-B',
    8: 'NC-B',
    11: 'FA-C',
    12: 'ND-C',
    13: 'NC-C',
    51: 'FA-M',
    201: 'FCE-A',
    206: 'FCE-B',
    211: 'FCE-C',
}

MAX_SCANNED_PDF_PAGES = 8
MAX_SCANNED_PDF_IMAGE_BYTES = 8 * 1024 * 1024
MAX_QR_IMAGE_BYTES = 8 * 1024 * 1024
MAX_QR_PDF_INPUT_BYTES = 40 * 1024 * 1024
MAX_QR_IMAGE_PIXELS = 20_000_000
ARCA_QR_NUMERIC_FIELD_PATTERN = re.compile(
    r'(?<!\\)(?P<prefix>"(?:ver|cuit|ptoVta|tipoCmp|nroCmp|importe|ctz|tipoDocRec|nroDocRec)"\s*:\s*)'
    r'0+(?P<number>\d+(?:\.\d+)?)(?=\s*[,}])'
)


def _normalize_afip_qr_numeric_literals(payload_text):
    """Accept fixed-width ARCA numeric fields such as ``ptoVta: 00003``.

    Some issued QR payloads encode integer values with leading zeroes even
    though they are unquoted JSON numbers. JSON rejects those literals, so
    normalize only the documented numeric fields and preserve their value.
    """
    def normalize(match):
        number = match.group('number')
        if '.' in number:
            integer, fraction = number.split('.', 1)
            number = f'{int(integer or 0)}.{fraction}'
        else:
            number = str(int(number))
        return match.group('prefix') + number

    return ARCA_QR_NUMERIC_FIELD_PATTERN.sub(normalize, payload_text)


class DolanOcrExtractor(models.AbstractModel):
    _name = 'dolan.ocr.extractor'
    _description = 'Motor de Extracción OCR con QR AFIP/ARCA + DOLAN AI (Sin IAP)'

    @api.model
    def decode_afip_qr_payload(self, b64_param):
        """Decodifica el parámetro `p` (Base64 JSON) de una URL QR oficial de AFIP/ARCA."""
        if not b64_param:
            return {}
        clean_b64 = urllib.parse.unquote(b64_param).strip()
        padding = '=' * (-len(clean_b64) % 4)
        try:
            raw_bytes = base64.urlsafe_b64decode(clean_b64 + padding)
            payload_text = raw_bytes.decode('utf-8', errors='replace')
            try:
                data = json.loads(payload_text)
            except json.JSONDecodeError:
                normalized_text = _normalize_afip_qr_numeric_literals(payload_text)
                if normalized_text == payload_text:
                    raise
                data = json.loads(normalized_text)
            if isinstance(data, dict):
                return {
                    'ver': data.get('ver', 1),
                    'fecha': data.get('fecha'),
                    'cuit': str(data.get('cuit') or '').replace('-', '').strip(),
                    'ptoVta': int(data.get('ptoVta') or 0),
                    'tipoCmp': int(data.get('tipoCmp') or 0),
                    'nroCmp': int(data.get('nroCmp') or 0),
                    'importe': float(data.get('importe') or 0.0),
                    'moneda': data.get('moneda') or 'PES',
                    'ctz': float(data.get('ctz') or 1.0),
                    'tipoDocRec': data.get('tipoDocRec'),
                    'nroDocRec': str(data.get('nroDocRec') or ''),
                    'tipoCodAut': data.get('tipoCodAut') or 'E',
                    'codAut': str(data.get('codAut') or ''),
                }
        except Exception as exc:
            _logger.debug("No se pudo decodificar payload Base64 de QR AFIP: %s", exc)
        return {}

    @api.model
    def extract_afip_qr_from_attachment(self, attachment):
        """Busca y decodifica URLs QR de AFIP/ARCA (`https://www.afip.gob.ar/fe/qr/?p=...`)
        dentro de los bytes o del texto indexado de un `ir.attachment`."""
        if not attachment:
            return {}
        candidates = []
        if attachment.index_content:
            candidates.append(attachment.index_content)
        if attachment.description:
            candidates.append(attachment.description)
        if attachment.raw:
            try:
                candidates.append(attachment.raw.decode('latin-1', errors='ignore'))
            except Exception:
                pass

        for text in candidates:
            match = AFIP_QR_REGEX.search(text or '')
            if match:
                decoded = self.decode_afip_qr_payload(match.group(1))
                if decoded and decoded.get('cuit'):
                    return decoded

        raw_content = attachment.raw
        if hasattr(raw_content, 'content'):
            raw_content = raw_content.content
        elif raw_content is not None and not isinstance(raw_content, bytes):
            raw_content = bytes(raw_content)
        if not raw_content:
            return {}

        mimetype = attachment.mimetype or ''
        if mimetype.startswith('image/'):
            if len(raw_content) > MAX_QR_IMAGE_BYTES:
                return {}
            return self._decode_afip_qr_image(raw_content)
        if mimetype == 'application/pdf' or (attachment.name or '').lower().endswith('.pdf'):
            if len(raw_content) > MAX_QR_PDF_INPUT_BYTES:
                return {}
            for image_bytes in self._render_pdf_pages_for_qr(raw_content):
                decoded = self._decode_afip_qr_image(image_bytes)
                if decoded:
                    return decoded
        return {}

    @api.model
    def _decode_afip_qr_image(self, image_bytes):
        """Decode a QR image locally and accept only the official ARCA/AFIP URL format."""
        if not image_bytes or len(image_bytes) > MAX_QR_IMAGE_BYTES:
            return {}
        try:
            import zxingcpp
            from PIL import Image
        except ImportError:
            _logger.warning('La lectura de QR en imagen requiere zxing-cpp y Pillow en el servidor.')
            return {}

        try:
            with Image.open(io.BytesIO(image_bytes)) as source_image:
                if source_image.width * source_image.height > MAX_QR_IMAGE_PIXELS:
                    return {}
                image = source_image.convert('RGB')
                barcodes = zxingcpp.read_barcodes(
                    image,
                    formats=zxingcpp.BarcodeFormat.QRCode,
                )
            for barcode in barcodes:
                match = AFIP_QR_REGEX.search(barcode.text or '')
                if match:
                    decoded = self.decode_afip_qr_payload(match.group(1))
                    if decoded and decoded.get('cuit'):
                        return decoded
        except Exception as exc:
            _logger.debug('No se pudo decodificar un QR fiscal en imagen (%s).', type(exc).__name__)
        return {}

    @api.model
    def _render_pdf_pages_for_qr(self, pdf_bytes):
        """Render up to eight bounded PDF pages for on-device QR decoding only."""
        try:
            import pymupdf
        except ImportError:
            _logger.warning('La lectura de QR en PDF requiere PyMuPDF en el servidor.')
            return []

        try:
            document = pymupdf.open(stream=pdf_bytes, filetype='pdf')
            rendered = []
            total_bytes = 0
            for page_number in range(min(document.page_count, MAX_SCANNED_PDF_PAGES)):
                page = document.load_page(page_number)
                rect = page.rect
                estimated_pixels = (rect.width * 160 / 72) * (rect.height * 160 / 72)
                if estimated_pixels > MAX_QR_IMAGE_PIXELS:
                    continue
                image_bytes = page.get_pixmap(
                    dpi=160,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                ).tobytes('png')
                if total_bytes + len(image_bytes) > MAX_QR_IMAGE_BYTES:
                    break
                rendered.append(image_bytes)
                total_bytes += len(image_bytes)
            return rendered
        except Exception as exc:
            _logger.debug('No se pudo renderizar un PDF para decodificar QR (%s).', type(exc).__name__)
            return []
        finally:
            if 'document' in locals():
                document.close()

    @api.model
    def extract_structured_document(self, attachment):
        """Combina la decodificación exacta del QR de AFIP/ARCA con la extracción estructurada
        mediante `dolan.ai.provider` (`DOLAN_ai`) sin consumir créditos IAP."""
        if not attachment:
            raise UserError(_('Adjuntá primero un archivo PDF o imagen del comprobante para digitalizarlo.'))

        raw_content = attachment.raw
        if hasattr(raw_content, 'content'):
            raw_content = raw_content.content
        elif raw_content is not None and not isinstance(raw_content, bytes):
            raw_content = bytes(raw_content)

        qr_data = self.extract_afip_qr_from_attachment(attachment)
        searchable_text = (attachment.index_content or '').strip()
        text_excerpt = searchable_text
        if not text_excerpt and raw_content:
            try:
                ascii_strings = re.findall(rb'[\x20-\x7E]{4,}', raw_content)
                text_excerpt = b'\n'.join(ascii_strings[:400]).decode('latin-1', errors='ignore')
            except Exception:
                text_excerpt = ''

        system_prompt = (
            "Sos el motor OCR Fiscal Argentino de DOLAN para Odoo 20. "
            "Analizá el comprobante adjunto y devolvé EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:\n"
            "{\n"
            '  "vendor_name": "Razón Social del Proveedor",\n'
            '  "vendor_cuit": "30112233445",\n'
            '  "invoice_date": "YYYY-MM-DD",\n'
            '  "pto_vta": 1,\n'
            '  "tipo_cmp": 1,\n'
            '  "nro_cmp": 1234,\n'
            '  "invoice_number": "FA-A 00001-00001234",\n'
            '  "currency": "ARS",\n'
            '  "cae": "74123456789012",\n'
            '  "lines": [\n'
            '    {"description": "Detalle del ítem", "quantity": 1.0, "price_unit": 1000.0, "iva_rate": 21.0}\n'
            '  ],\n'
            '  "taxes": {"iva_21": 210.0, "iva_105": 0.0, "iva_27": 0.0, "percepcion_iibb": 0.0},\n'
            '  "total": 1210.0\n'
            "}\n"
            "No inventes renglones ni alícuotas a partir del importe total. "
            "Transcribí las descripciones literalmente: no completes abreviaturas ni agregues texto deducido. "
            "Si el detalle no es legible, devolvé lines como [] y taxes como {}. "
            "No calcules IVA ni percepciones desde el total."
        )

        user_content = [
            {
                'type': 'text',
                'text': (
                    f"Archivo: {attachment.name}\n"
                    f"Datos QR AFIP detectados previamente: {json.dumps(qr_data, ensure_ascii=False)}\n"
                    f"Texto extraído del documento:\n{text_excerpt[:6000]}"
                ),
            }
        ]
        vision_images = []
        if raw_content and attachment.mimetype and attachment.mimetype.startswith('image/'):
            vision_images.append((attachment.mimetype, raw_content))
        elif (
            raw_content
            and (attachment.mimetype == 'application/pdf' or (attachment.name or '').lower().endswith('.pdf'))
            and len(searchable_text) < 160
        ):
            vision_images = self._render_scanned_pdf_pages(raw_content)

        for mimetype, image_bytes in vision_images:
            b64_str = base64.b64encode(image_bytes).decode('ascii')
            user_content.append({
                'type': 'image_url',
                'image_url': {'url': f"data:{mimetype};base64,{b64_str}", 'detail': 'high'},
            })

        provider = self.env['dolan.ai.provider'].get_active_provider()
        completion = provider.generate_completion(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content if len(user_content) > 1 else user_content[0]['text']},
            ],
            temperature=0.0,
        )

        ai_parsed = self._parse_json_from_completion(completion.get('content') or '')
        return self._merge_qr_and_ai_results(qr_data, ai_parsed, text_excerpt, attachment.name)

    @api.model
    def _render_scanned_pdf_pages(self, pdf_bytes):
        """Render a bounded scanned PDF to PNG pages for the configured vision provider."""
        try:
            import pymupdf
        except ImportError as exc:
            raise UserError(_('El OCR de PDFs escaneados requiere PyMuPDF en el servidor.')) from exc

        try:
            document = pymupdf.open(stream=pdf_bytes, filetype='pdf')
            if not document.page_count:
                raise UserError(_('El PDF no contiene páginas para digitalizar.'))
            if document.page_count > MAX_SCANNED_PDF_PAGES:
                raise UserError(_(
                    'El PDF tiene %s páginas; el OCR visual admite hasta %s por comprobante.'
                ) % (document.page_count, MAX_SCANNED_PDF_PAGES))

            rendered = []
            total_bytes = 0
            for page in document:
                pixmap = page.get_pixmap(dpi=160, colorspace=pymupdf.csRGB, alpha=False)
                image_bytes = pixmap.tobytes('png')
                total_bytes += len(image_bytes)
                if total_bytes > MAX_SCANNED_PDF_IMAGE_BYTES:
                    raise UserError(_('Las imágenes del PDF superan el límite de tamaño para OCR visual.'))
                rendered.append(('image/png', image_bytes))
            return rendered
        except UserError:
            raise
        except Exception as exc:
            _logger.warning('No se pudo renderizar un PDF escaneado para OCR (%s)', type(exc).__name__)
            raise UserError(_('No se pudo leer o renderizar el PDF adjunto para OCR visual.')) from exc
        finally:
            if 'document' in locals():
                document.close()

    @staticmethod
    def _parse_json_from_completion(raw_text):
        if not raw_text:
            return {}
        cleaned = raw_text.strip()
        if '```' in cleaned:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        brace_start = cleaned.find('{')
        brace_end = cleaned.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(cleaned[brace_start:brace_end + 1])
            except Exception:
                return {}
        return {}

    def _merge_qr_and_ai_results(self, qr_data, ai_data, text_excerpt, filename):
        """Combina con prioridad fiscal los datos exactos del QR de AFIP/ARCA y el desglose de líneas de la IA."""
        cuit = qr_data.get('cuit') or ai_data.get('vendor_cuit') or ''
        if not cuit and text_excerpt:
            cuit_match = re.search(r'\b(20|23|24|27|30|33|34)[-]?(\d{8})[-]?(\d)\b', text_excerpt)
            if cuit_match:
                cuit = ''.join(cuit_match.groups())

        pto_vta = qr_data.get('ptoVta') or ai_data.get('pto_vta') or 1
        tipo_cmp = qr_data.get('tipoCmp') or ai_data.get('tipo_cmp') or 1
        nro_cmp = qr_data.get('nroCmp') or ai_data.get('nro_cmp') or 0
        prefix = AFIP_TIPO_CMP_MAP.get(int(tipo_cmp), 'FA-A')
        formatted_number = (
            f"{prefix} {int(pto_vta):05d}-{int(nro_cmp):08d}"
            if nro_cmp
            else (ai_data.get('invoice_number') or filename or 'S/N')
        )

        total = float(qr_data.get('importe') or ai_data.get('total') or 0.0)
        validation_warnings = []
        qr_total = float(qr_data.get('importe') or 0.0)
        document_total = float(ai_data.get('total') or 0.0)
        if qr_total and document_total and abs(qr_total - document_total) > 0.01:
            validation_warnings.append(_(
                'El total del QR ARCA (%(qr_total).2f) difiere del total leído del comprobante '
                '(%(document_total).2f). Revisar ambos valores antes de contabilizar.'
            ) % {'qr_total': qr_total, 'document_total': document_total})
        lines = ai_data.get('lines')
        if not isinstance(lines, list):
            lines = []
        taxes = ai_data.get('taxes')
        if not isinstance(taxes, dict):
            taxes = {}
        if lines and document_total:
            try:
                line_subtotal = sum(
                    float(line.get('quantity') or 1.0) * float(line.get('price_unit') or 0.0)
                    for line in lines
                    if isinstance(line, dict)
                )
                parsed_tax_amounts = [float(amount or 0.0) for amount in taxes.values()]
                line_total_with_taxes = line_subtotal + sum(parsed_tax_amounts)
                if (
                    abs(document_total - line_subtotal) > 0.01
                    and abs(document_total - line_total_with_taxes) > 0.01
                ):
                    validation_warnings.append(_(
                        'El total leído por OCR (%(document_total).2f) no coincide con la suma de líneas '
                        '(%(line_subtotal).2f) ni con líneas más impuestos (%(line_total).2f). Revisar el desglose.'
                    ) % {
                        'document_total': document_total,
                        'line_subtotal': line_subtotal,
                        'line_total': line_total_with_taxes,
                    })
            except (TypeError, ValueError):
                validation_warnings.append(_(
                    'No se pudo validar la consistencia aritmética del desglose OCR. Revisar líneas e impuestos.'
                ))

        moneda_qr = qr_data.get('moneda') or ai_data.get('currency') or 'ARS'
        currency_code = 'USD' if moneda_qr in ('DOL', 'USD') else 'ARS'

        return {
            'source': 'qr_and_ai' if qr_data else 'ai_only',
            'vendor_name': ai_data.get('vendor_name') or (f"Proveedor CUIT {cuit}" if cuit else 'Proveedor Digitalizado'),
            'vendor_cuit': cuit,
            'invoice_date': qr_data.get('fecha') or ai_data.get('invoice_date') or fields.Date.context_today(self).isoformat(),
            'pto_vta': pto_vta,
            'tipo_cmp': tipo_cmp,
            'nro_cmp': nro_cmp,
            'invoice_number': formatted_number,
            'cae': qr_data.get('codAut') or ai_data.get('cae') or '',
            'currency': currency_code,
            'lines': lines,
            'taxes': taxes,
            'total': total,
            'validation_warnings': validation_warnings,
            'qr_raw': qr_data,
        }


class AccountMoveDolanOcr(models.Model):
    _inherit = 'account.move'

    dolan_ocr_status = fields.Selection(
        selection=[
            ('none', 'Sin Digitalizar'),
            ('qr_extracted', 'Extraído con QR AFIP + IA'),
            ('ai_extracted', 'Extraído con DOLAN IA'),
            ('error', 'Error de Extracción'),
        ],
        string='Estado OCR DOLAN',
        default='none',
        copy=False,
    )
    dolan_ocr_cae = fields.Char(
        string='CAE Candidato Extraído (sin validar)',
        copy=False,
        help='Dato sugerido por OCR/QR. Revisalo contra el comprobante antes de aplicarlo al CAE fiscal.',
    )
    dolan_ocr_qr_payload = fields.Text(
        string='Payload QR AFIP Decodificado',
        copy=False,
    )
    dolan_ocr_raw_json = fields.Text(
        string='JSON Estructurado DOLAN OCR',
        copy=False,
    )
    dolan_ocr_warnings = fields.Text(
        string='Advertencias de revisión OCR',
        copy=False,
        help='Diferencias entre QR y lectura del comprobante que requieren revisión manual.',
    )
    dolan_ocr_duplicate_id = fields.Many2one(
        'account.move',
        string='Posible comprobante duplicado',
        readonly=True,
        copy=False,
        help='Coincide el proveedor y el número de comprobante o CAE con otro documento no cancelado. Revisá ambos antes de continuar.',
    )
    dolan_ocr_duplicate_reason = fields.Selection(
        selection=[
            ('reference', 'Coincide proveedor y número de comprobante'),
            ('cae', 'Coincide proveedor y CAE'),
        ],
        string='Motivo posible duplicado',
        readonly=True,
        copy=False,
    )

    def _get_ocr_candidate_attachment(self):
        self.ensure_one()
        if self.message_main_attachment_id:
            return self.message_main_attachment_id
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
        ], order='id desc', limit=1)

    def _find_or_create_partner_by_cuit(self, cuit, vendor_name):
        Partner = self.env['res.partner']
        clean_cuit = (cuit or '').replace('-', '').strip()
        if clean_cuit:
            partner = Partner.search([
                '|',
                ('vat', 'ilike', clean_cuit),
                ('vat', 'ilike', f"{clean_cuit[:2]}-{clean_cuit[2:10]}-{clean_cuit[10:]}"),
            ], limit=1)
            if partner:
                return partner
        if vendor_name:
            partner = Partner.search([('name', '=ilike', vendor_name)], limit=1)
            if partner:
                return partner
        if clean_cuit or vendor_name:
            return Partner.create({
                'name': vendor_name or f'Proveedor {clean_cuit}',
                'vat': clean_cuit or False,
                'supplier_rank': 1,
                # Odoo 20 derives company_type from is_company; it is not a
                # writable partner field and would make OCR vendor creation fail.
                'is_company': True,
            })
        return Partner.browse()

    def _match_purchase_tax(self, iva_rate):
        if not iva_rate:
            return self.env['account.tax'].browse()
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', float(iva_rate)),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _find_ocr_duplicate(self, partner, invoice_number, cae):
        """Find an existing same-company supplier document worth reviewing.

        Matching is a warning only: OCR guesses and supplier references are not
        strong enough to block a human from recording a legitimate document.
        """
        self.ensure_one()
        if not partner:
            return self.env['account.move'].browse(), False
        candidates = self.env['account.move'].search([
            ('id', '!=', self.id),
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', partner.id),
            ('move_type', 'in', ('in_invoice', 'in_refund', 'in_receipt')),
            ('state', '!=', 'cancel'),
        ], order='id desc')
        normalized_reference = ''.join(char for char in (invoice_number or '').upper() if char.isalnum())
        for candidate in candidates:
            candidate_references = {
                ''.join(char for char in (reference or '').upper() if char.isalnum())
                for reference in (candidate.ref, candidate.l10n_latam_document_number)
            }
            if normalized_reference and normalized_reference in candidate_references:
                return candidate, 'reference'
            if cae and cae in (candidate.dolan_ocr_cae, candidate.l10n_ar_afip_auth_code):
                return candidate, 'cae'
        return self.env['account.move'].browse(), False

    def action_dolan_ocr_extract(self):
        """Digitaliza la factura de proveedor sin usar créditos IAP:
        1. Decodifica el QR oficial de AFIP/ARCA si está presente.
        2. Extrae proveedor, fecha, número, CAE, líneas e impuestos con DOLAN AI."""
        Extractor = self.env['dolan.ocr.extractor']
        for move in self:
            if move.state != 'draft':
                raise UserError(_('Solo se pueden digitalizar comprobantes en estado Borrador.'))
            attachment = move._get_ocr_candidate_attachment()
            if not attachment:
                raise UserError(_('Adjuntá primero el PDF o imagen de la factura en el Chatter antes de digitalizar.'))

            extracted = Extractor.extract_structured_document(attachment)
            partner = move._find_or_create_partner_by_cuit(
                extracted.get('vendor_cuit'),
                extracted.get('vendor_name'),
            )
            duplicate, duplicate_reason = move._find_ocr_duplicate(
                partner,
                extracted.get('invoice_number'),
                extracted.get('cae'),
            )

            vals = {
                'dolan_ocr_status': 'qr_extracted' if extracted.get('source') == 'qr_and_ai' else 'ai_extracted',
                'dolan_ocr_cae': extracted.get('cae') or False,
                'dolan_ocr_qr_payload': json.dumps(extracted.get('qr_raw') or {}, ensure_ascii=False, indent=2),
                'dolan_ocr_raw_json': json.dumps(extracted, ensure_ascii=False, indent=2),
                'dolan_ocr_warnings': '\n'.join(extracted.get('validation_warnings') or []) or False,
                'dolan_ocr_duplicate_id': duplicate.id or False,
                'dolan_ocr_duplicate_reason': duplicate_reason or False,
                'ref': extracted.get('invoice_number') or move.ref,
                'invoice_date': extracted.get('invoice_date') or move.invoice_date,
            }
            document_type = self.env['l10n_latam.document.type'].search([
                ('country_id.code', '=', 'AR'),
                ('code', '=', str(extracted.get('tipo_cmp') or '')),
            ], limit=1)
            document_number = False
            if extracted.get('pto_vta') and extracted.get('nro_cmp'):
                document_number = (
                    f"{int(extracted['pto_vta']):05d}-{int(extracted['nro_cmp']):08d}"
                )
            expected_move_types = {
                'invoice': ('in_invoice', 'in_receipt'),
                'debit_note': ('in_invoice',),
                'credit_note': ('in_refund',),
            }
            if (
                document_type
                and move.move_type in expected_move_types.get(document_type.internal_type, ())
            ):
                vals['l10n_latam_document_type_id'] = document_type.id
                if document_number:
                    vals['l10n_latam_document_number'] = document_number
            if partner:
                vals['partner_id'] = partner.id

            if not move.invoice_line_ids and extracted.get('lines'):
                line_commands = []
                for ln in extracted['lines']:
                    tax = move._match_purchase_tax(ln.get('iva_rate'))
                    line_vals = {
                        'name': ln.get('description') or _('Ítem digitalizado'),
                        'quantity': float(ln.get('quantity') or 1.0),
                        'price_unit': float(ln.get('price_unit') or 0.0),
                    }
                    if tax:
                        line_vals['tax_ids'] = [(6, 0, [tax.id])]
                    line_commands.append((0, 0, line_vals))
                vals['invoice_line_ids'] = line_commands

            move.write(vals)
            move.message_post(
                body=_(
                    "<strong>Comprobante digitalizado con DOLAN IA (Sin IAP)</strong><ul>"
                    "<li>Proveedor: %s (CUIT: %s)</li>"
                    "<li>Comprobante: %s | Fecha: %s</li>"
                    "<li>Importe Total: %s %s | CAE: %s</li>"
                    "</ul>"
                ) % (
                    extracted.get('vendor_name') or '-',
                    extracted.get('vendor_cuit') or '-',
                    extracted.get('invoice_number') or '-',
                    extracted.get('invoice_date') or '-',
                    extracted.get('currency') or 'ARS',
                    extracted.get('total') or 0.0,
                    extracted.get('cae') or 'N/A',
                )
            )
        return True

    def action_dolan_ocr_apply_cae(self):
        """Aplica al campo fiscal el CAE candidato después de revisión humana.

        La extracción no es una consulta a ARCA y por eso no marca el resultado
        como aprobado ni inventa una fecha de vencimiento.
        """
        for move in self:
            if move.state != 'draft' or move.move_type not in ('in_invoice', 'in_refund', 'in_receipt'):
                raise UserError(_('Solo se puede aplicar un CAE revisado en una factura de proveedor borrador.'))
            cae = re.sub(r'\s+', '', move.dolan_ocr_cae or '')
            if not cae.isdigit() or len(cae) != 14:
                raise UserError(_('El CAE candidato debe contener exactamente 14 dígitos.'))
            if move.l10n_ar_afip_auth_code and move.l10n_ar_afip_auth_code != cae:
                raise UserError(_('Ya existe un CAE fiscal distinto. Revisá el comprobante antes de cambiarlo.'))

            qr_data = {}
            try:
                qr_data = json.loads(move.dolan_ocr_qr_payload or '{}')
            except (TypeError, ValueError):
                pass
            auth_mode = 'CAEA' if qr_data.get('tipoCodAut') == 'A' else 'CAE'
            move.write({
                'l10n_ar_afip_auth_code': cae,
                'l10n_ar_afip_auth_mode': auth_mode,
            })
            move.message_post(body=_(
                'CAE de comprobante proveedor aplicado desde el candidato OCR tras revisión del usuario. '
                'La extracción no consulta ni confirma la autorización en ARCA.'
            ))
        return True


class HrExpenseDolanOcr(models.Model):
    _inherit = 'hr.expense'

    dolan_ocr_status = fields.Selection(
        selection=[
            ('none', 'Sin Digitalizar'),
            ('qr_extracted', 'Extraído con QR AFIP + IA'),
            ('ai_extracted', 'Extraído con DOLAN IA'),
            ('error', 'Error de Extracción'),
        ],
        string='Estado OCR DOLAN',
        default='none',
        copy=False,
    )
    dolan_ocr_cae = fields.Char(
        string='CAE Extraído (OCR/QR)',
        copy=False,
    )
    dolan_ocr_raw_json = fields.Text(
        string='JSON Estructurado DOLAN OCR',
        copy=False,
    )
    dolan_ocr_warnings = fields.Text(
        string='Advertencias de revisión OCR',
        copy=False,
        help='Diferencias entre QR y lectura del comprobante que requieren revisión manual.',
    )

    def _get_ocr_candidate_attachment(self):
        self.ensure_one()
        if self.message_main_attachment_id:
            return self.message_main_attachment_id
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'hr.expense'),
            ('res_id', '=', self.id),
        ], order='id desc', limit=1)

    def action_dolan_ocr_extract(self):
        """Digitaliza un ticket o factura de gasto en `hr.expense` usando QR AFIP/ARCA + DOLAN IA."""
        Extractor = self.env['dolan.ocr.extractor']
        for expense in self:
            attachment = expense._get_ocr_candidate_attachment()
            if not attachment:
                raise UserError(_('Adjuntá primero el comprobante o foto del ticket de gasto antes de digitalizar.'))

            extracted = Extractor.extract_structured_document(attachment)
            vals = {
                'dolan_ocr_status': 'qr_extracted' if extracted.get('source') == 'qr_and_ai' else 'ai_extracted',
                'dolan_ocr_cae': extracted.get('cae') or False,
                'dolan_ocr_raw_json': json.dumps(extracted, ensure_ascii=False, indent=2),
                'dolan_ocr_warnings': '\n'.join(extracted.get('validation_warnings') or []) or False,
                'name': f"{extracted.get('vendor_name', 'Gasto')} - {extracted.get('invoice_number', '')}".strip(' -'),
                'date': extracted.get('invoice_date') or expense.date,
            }
            total = float(extracted.get('total') or 0.0)
            if total > 0:
                if 'total_amount_currency' in expense._fields:
                    vals['total_amount_currency'] = total
                elif 'price_unit' in expense._fields:
                    vals['price_unit'] = total

            expense.write(vals)
            expense.message_post(
                body=_(
                    "<strong>Gasto digitalizado con DOLAN IA (Sin IAP)</strong>: "
                    "%s — Comprobante %s — Total: %s %s (CAE: %s)"
                ) % (
                    extracted.get('vendor_name') or '-',
                    extracted.get('invoice_number') or '-',
                    extracted.get('currency') or 'ARS',
                    total,
                    extracted.get('cae') or 'N/A',
                )
            )
        return True
