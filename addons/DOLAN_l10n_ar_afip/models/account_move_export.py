# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Factura E de exportación (WSFEXv1) y factura con detalle (WSMTXCA)."""

import xml.etree.ElementTree as ET

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

WSFEX_NS = 'http://ar.gov.afip.dif.fexv1/'
WSMTXCA_NS = 'http://impl.service.wsmtxca.afip.gov.ar/service/'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'

EXPORT_CODES = {'19': 'invoice', '20': 'debit_note', '21': 'credit_note'}
MTXCA_CODES = {
    ('out_invoice', 'invoice'): {'1', '6'},
    ('out_invoice', 'debit_note'): {'2', '7'},
    ('out_refund', 'credit_note'): {'3', '8'},
}
VAT_IDS = {'1', '2', '3', '4', '5', '6', '8', '9'}


def _local(node):
    return node.tag.split('}')[-1]


def _digits(value):
    return ''.join(char for char in (value or '') if char.isdigit())


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ar_journal_pos_system = fields.Selection(
        related='journal_id.l10n_ar_afip_pos_system',
        string='Sistema del punto de venta',
    )
    l10n_ar_export_permit_existing = fields.Selection(
        [('S', 'Sí'), ('N', 'No')],
        string='¿Tiene permiso de embarque?',
        copy=False,
        help='Obligatorio en Factura E de bienes (tipo 19). No corresponde para servicios ni notas.',
    )
    l10n_ar_export_permit_number = fields.Char(
        string='Permiso de embarque',
        size=16,
        copy=False,
        help='Número de destinación de 16 caracteres otorgado por Aduana.',
    )
    l10n_ar_export_permit_country_id = fields.Many2one(
        'res.country',
        string='País de destino de la mercadería',
        copy=False,
    )
    l10n_ar_export_language = fields.Selection(
        [('1', 'Español'), ('2', 'Inglés'), ('3', 'Portugués')],
        string='Idioma del comprobante',
        default='1',
        copy=False,
    )
    l10n_ar_export_commercial_notes = fields.Char(
        string='Observaciones comerciales (exportación)',
        size=1000,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _l10n_ar_ws_common_checks(self, conn, service):
        self.ensure_one()
        if self.state != 'posted' or not self.invoice_date:
            raise UserError(_('Publique el comprobante y complete su fecha antes de pedir el CAE.'))
        if not conn or conn.is_simulated or conn.l10n_ar_afip_ws != service:
            raise UserError(_('La solicitud requiere una conexión %s real, no simulada.') % service.upper())
        if not conn.token or not conn.sign:
            raise UserError(_('La conexión %s no tiene un ticket de acceso vigente.') % service.upper())
        cuit = _digits(self.company_id.vat)
        if self.company_id.country_id.code != 'AR' or len(cuit) != 11:
            raise UserError(_('Configure un CUIT argentino de 11 dígitos para la compañía emisora.'))
        pos_number = self.journal_id.l10n_ar_afip_pos_number
        if not pos_number or pos_number <= 0:
            raise UserError(_('Configure el punto de venta ARCA en el diario de ventas.'))
        document_type = self.l10n_latam_document_type_id
        try:
            parts = self._l10n_ar_get_document_number_parts(self.l10n_latam_document_number, str(document_type.code))
            number = int(parts['invoice_number'])
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise UserError(_('El comprobante no tiene un número fiscal argentino válido.')) from exc
        if number <= 0:
            raise UserError(_('El número fiscal debe ser positivo.'))
        product_lines = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        if not product_lines:
            raise UserError(_('El comprobante no tiene líneas de producto.'))
        return cuit, pos_number, number, product_lines

    def _l10n_ar_currency_values(self):
        """ARCA currency code and rate (ARS per unit of the document currency)."""
        self.ensure_one()
        currency = self.currency_id
        code = (currency.l10n_ar_afip_code or '').strip()
        if not code:
            raise UserError(_('La moneda %s no tiene código ARCA.') % currency.name)
        if currency == self.company_id.currency_id:
            return code, 1.0
        rate = self.invoice_currency_rate
        if not rate:
            raise UserError(_('El comprobante en %s no tiene cotización.') % currency.name)
        return code, round(1.0 / rate, 6)

    def _l10n_ar_associated_document(self):
        self.ensure_one()
        if self.move_type == 'out_refund':
            return self.reversed_entry_id
        if 'debit_origin_id' in self._fields:
            return self.debit_origin_id
        return self.browse()

    def _l10n_ar_store_authorization(self, cae, due_date, result, req_xml, resp_xml):
        request_root = ET.fromstring(req_xml)
        for node in request_root.iter():
            if _local(node) in ('Token', 'Sign', 'token', 'sign'):
                node.text = '[REDACTED]'
        self.write({
            'l10n_ar_afip_auth_mode': 'CAE',
            'l10n_ar_afip_auth_code': cae,
            'l10n_ar_afip_auth_code_due': due_date,
            'l10n_ar_afip_result': result,
            'l10n_ar_afip_xml_request': ET.tostring(request_root, encoding='unicode'),
            'l10n_ar_afip_xml_response': resp_xml,
        })

    # ------------------------------------------------------------------
    # WSFEXv1: Factura E
    # ------------------------------------------------------------------
    def _l10n_ar_build_wsfex_request_xml(self, conn, request_id):
        """Build a validated ``FEXAuthorize`` request for a Factura/Nota E."""
        cuit, pos_number, number, lines = self._l10n_ar_ws_common_checks(conn, 'wsfex')
        document_code = str(self.l10n_latam_document_type_id.code or '').strip()
        if document_code not in EXPORT_CODES:
            raise UserError(_('WSFEX solo emite Facturas, Notas de Débito y Notas de Crédito E (19, 20 y 21).'))
        if self.currency_id.compare_amounts(self.amount_tax, 0.0):
            raise UserError(_('Una Factura E no lleva IVA ni otros tributos: quite los impuestos de las líneas.'))
        concept = self.l10n_ar_afip_concept
        export_type = {'1': '1', '2': '2', '4': '4'}.get(concept)
        if not export_type:
            raise UserError(_('El concepto de exportación debe ser bienes, servicios u otros.'))

        partner = self.commercial_partner_id
        country = partner.country_id
        if not country or country.code == 'AR':
            raise UserError(_('El cliente del exterior debe tener un país distinto de Argentina.'))
        destination = (country.l10n_ar_afip_code or '').strip()
        if not destination:
            raise UserError(_('El país %s no tiene código ARCA de destino.') % country.name)
        country_cuit = _digits(country.l10n_ar_legal_entity_vat if partner.is_company else country.l10n_ar_natural_vat)
        tax_id = (partner.vat or '').strip()
        if not country_cuit and not tax_id:
            raise UserError(_('Informe la identificación fiscal del cliente o el CUIT genérico del país.'))
        address = ', '.join(filter(None, [partner.street, partner.street2, partner.city, partner.zip, country.name]))
        if not address:
            raise UserError(_('Complete el domicilio del cliente del exterior.'))

        permit_existing = ''
        permits = []
        if document_code == '19' and export_type == '1':
            permit_existing = self.l10n_ar_export_permit_existing or ''
            if not permit_existing:
                raise UserError(_('Indique si la Factura E de bienes tiene permiso de embarque.'))
            if permit_existing == 'S':
                permit = (self.l10n_ar_export_permit_number or '').strip().upper()
                permit_country = self.l10n_ar_export_permit_country_id or country
                if len(permit) != 16 or not permit.isalnum():
                    raise UserError(_('El permiso de embarque debe tener 16 caracteres alfanuméricos.'))
                if not permit_country.l10n_ar_afip_code:
                    raise UserError(_('El país de destino de la mercadería no tiene código ARCA.'))
                permits.append((permit, permit_country.l10n_ar_afip_code))
        incoterm = self.invoice_incoterm_id
        if export_type == '1' and document_code == '19' and not incoterm:
            raise UserError(_('Las exportaciones de bienes requieren Incoterm.'))

        associated = self._l10n_ar_associated_document()
        if document_code in ('20', '21'):
            if not associated or associated.l10n_latam_document_type_id.code not in EXPORT_CODES:
                raise UserError(_('Las notas E requieren una Factura E asociada.'))
            if not associated.l10n_ar_afip_auth_code:
                raise UserError(_('La Factura E asociada todavía no tiene CAE.'))
        if export_type in ('2', '4') and not self.invoice_date_due:
            raise UserError(_('Las exportaciones de servicios requieren fecha de pago (vencimiento).'))

        currency_code, rate = self._l10n_ar_currency_values()
        currency = self.currency_id
        items = []
        for line in lines:
            uom_code = (line.product_uom_id.l10n_ar_afip_code or '').strip()
            if not uom_code:
                raise UserError(_('La unidad de medida %s no tiene código ARCA.') % line.product_uom_id.name)
            gross = line.quantity * line.price_unit
            items.append((
                line.product_id.default_code or str(line.product_id.id or ''),
                (line.name or line.product_id.display_name or '')[:4000],
                f'{line.quantity:.6f}',
                uom_code,
                f'{line.price_unit:.6f}',
                f'{currency.round(gross - line.price_subtotal):.2f}',
                f'{currency.round(line.price_subtotal):.2f}',
            ))

        ns = WSFEX_NS
        ET.register_namespace('soapenv', SOAP_NS)
        ET.register_namespace('ar', ns)
        envelope = ET.Element(f'{{{SOAP_NS}}}Envelope')
        body = ET.SubElement(envelope, f'{{{SOAP_NS}}}Body')
        operation = ET.SubElement(body, f'{{{ns}}}FEXAuthorize')

        def add(parent, tag, value=None):
            node = ET.SubElement(parent, f'{{{ns}}}{tag}')
            if value is not None:
                node.text = str(value)
            return node

        auth = add(operation, 'Auth')
        add(auth, 'Token', conn.token)
        add(auth, 'Sign', conn.sign)
        add(auth, 'Cuit', cuit)
        cmp = add(operation, 'Cmp')
        add(cmp, 'Id', request_id)
        add(cmp, 'Fecha_cbte', self.invoice_date.strftime('%Y%m%d'))
        add(cmp, 'Cbte_Tipo', document_code)
        add(cmp, 'Punto_vta', pos_number)
        add(cmp, 'Cbte_nro', number)
        add(cmp, 'Tipo_expo', export_type)
        add(cmp, 'Permiso_existente', permit_existing)
        if permits:
            permits_node = add(cmp, 'Permisos')
            for permit, permit_country in permits:
                item = add(permits_node, 'Permiso')
                add(item, 'Id_permiso', permit)
                add(item, 'Dst_merc', permit_country)
        add(cmp, 'Dst_cmp', destination)
        add(cmp, 'Cliente', (partner.name or '')[:200])
        add(cmp, 'Cuit_pais_cliente', country_cuit or '')
        add(cmp, 'Domicilio_cliente', address[:300])
        add(cmp, 'Id_impositivo', tax_id[:50])
        add(cmp, 'Moneda_Id', currency_code)
        add(cmp, 'Moneda_ctz', f'{rate:.6f}')
        add(cmp, 'Obs_comerciales', (self.l10n_ar_export_commercial_notes or '')[:1000])
        add(cmp, 'Imp_total', f'{currency.round(self.amount_total):.2f}')
        add(cmp, 'Obs', html2plaintext(self.narration or '')[:1000] if self.narration else '')
        if document_code in ('20', '21'):
            assoc_parts = associated._l10n_ar_get_document_number_parts(
                associated.l10n_latam_document_number, str(associated.l10n_latam_document_type_id.code),
            )
            assoc_node = add(add(cmp, 'Cmps_asoc'), 'Cmp_asoc')
            add(assoc_node, 'Cbte_tipo', associated.l10n_latam_document_type_id.code)
            add(assoc_node, 'Cbte_punto_vta', associated.journal_id.l10n_ar_afip_pos_number)
            add(assoc_node, 'Cbte_nro', assoc_parts['invoice_number'])
            add(assoc_node, 'Cbte_cuit', cuit)
        add(cmp, 'Forma_pago', (self.invoice_payment_term_id.name or '')[:50])
        add(cmp, 'Incoterms', (incoterm.code or '') if incoterm else '')
        add(cmp, 'Incoterms_Ds', (incoterm.name or '')[:20] if incoterm else '')
        add(cmp, 'Idioma_cbte', self.l10n_ar_export_language or '1')
        items_node = add(cmp, 'Items')
        for code, description, qty, uom_code, price, discount, total in items:
            item = add(items_node, 'Item')
            add(item, 'Pro_codigo', code[:30])
            add(item, 'Pro_ds', description)
            add(item, 'Pro_qty', qty)
            add(item, 'Pro_umed', uom_code)
            add(item, 'Pro_precio_uni', price)
            add(item, 'Pro_bonificacion', discount)
            add(item, 'Pro_total_item', total)
        if export_type in ('2', '4'):
            add(cmp, 'Fecha_pago', self.invoice_date_due.strftime('%Y%m%d'))
        return ET.tostring(envelope, encoding='utf-8', xml_declaration=True).decode('utf-8')

    def _l10n_ar_wsfex_simple_call(self, conn, method):
        envelope = ET.Element(f'{{{SOAP_NS}}}Envelope')
        body = ET.SubElement(envelope, f'{{{SOAP_NS}}}Body')
        operation = ET.SubElement(body, f'{{{WSFEX_NS}}}{method}')
        auth = ET.SubElement(operation, f'{{{WSFEX_NS}}}Auth')
        for key, value in (('Token', conn.token), ('Sign', conn.sign), ('Cuit', _digits(self.company_id.vat))):
            ET.SubElement(auth, f'{{{WSFEX_NS}}}{key}').text = str(value or '')
        return conn._ws_post_envelope(
            ET.tostring(envelope, encoding='utf-8', xml_declaration=True), 'wsfex', f'{WSFEX_NS}{method}', method,
        )

    @staticmethod
    def _l10n_ar_wsfex_errors(root):
        messages = []
        for node in root.iter():
            if _local(node) not in ('FEXErr', 'FEXEvents'):
                continue
            values = {_local(child): (child.text or '').strip() for child in node}
            code = values.get('ErrCode') or values.get('EventCode') or ''
            message = values.get('ErrMsg') or values.get('EventMsg') or ''
            if code and code != '0':
                messages.append(f'{code}: {message}'[:300])
        return messages

    def _l10n_ar_request_cae_wsfex(self, conn):
        self.ensure_one()
        last = self._l10n_ar_wsfex_simple_call(conn, 'FEXGetLast_ID')
        last_id = next((
            (node.text or '').strip() for node in last.iter() if _local(node) == 'Id'
        ), '')
        if not last_id.isdigit():
            raise UserError(_('ARCA no devolvió el último identificador WSFEX. %s') % '; '.join(self._l10n_ar_wsfex_errors(last)))
        req_xml = self._l10n_ar_build_wsfex_request_xml(conn, int(last_id) + 1)
        root = conn._ws_post_envelope(req_xml, 'wsfex', f'{WSFEX_NS}FEXAuthorize', 'FEXAuthorize')
        result = next((node for node in root.iter() if _local(node) == 'FEXResultAuth'), None)
        values = {_local(child): (child.text or '').strip() for child in result} if result is not None else {}
        cae, due = values.get('Cae', ''), values.get('Fch_venc_Cae', '')
        errors = self._l10n_ar_wsfex_errors(root)
        if values.get('Resultado') != 'A' or not (cae.isdigit() and len(cae) == 14) or len(due) != 8:
            suffix = (' ' + '; '.join(errors)) if errors else ''
            raise UserError(_('ARCA no autorizó la Factura E. No se generó ningún CAE local.%s') % suffix)
        self._l10n_ar_store_authorization(
            cae, fields.Date.to_date(f'{due[:4]}-{due[4:6]}-{due[6:8]}'),
            'O' if values.get('Motivos_Obs') else 'A', req_xml, ET.tostring(root, encoding='unicode'),
        )

    # ------------------------------------------------------------------
    # WSMTXCA: factura con detalle de ítems
    # ------------------------------------------------------------------
    def _l10n_ar_build_wsmtxca_request_xml(self, conn):
        """Build a validated ``autorizarComprobante`` request (A/B with item detail)."""
        cuit, pos_number, number, lines = self._l10n_ar_ws_common_checks(conn, 'wsmtxca')
        document_type = self.l10n_latam_document_type_id
        document_code = str(document_type.code or '').strip()
        if document_code not in MTXCA_CODES.get((self.move_type, document_type.internal_type), set()):
            raise UserError(_('WSMTXCA emite facturas y notas A y B; otros comprobantes siguen bloqueados.'))
        letter = document_type.l10n_ar_letter
        if (self.company_id.l10n_ar_afip_responsibility_type_id.code or '').strip() != '1':
            raise UserError(_('WSMTXCA requiere una compañía emisora Responsable Inscripta.'))
        doc_type = (self.partner_id.l10n_ar_afip_code or '').strip()
        doc_number = _digits(self.partner_id.l10n_ar_afip_id_value)
        if not doc_type.isdigit() or not doc_number:
            raise UserError(_('Complete el tipo y número de documento fiscal del destinatario.'))
        concept = self.l10n_ar_afip_concept
        if concept not in ('1', '2', '3'):
            raise UserError(_('WSMTXCA solo admite productos, servicios o ambos.'))
        if concept in ('2', '3') and not (
            self.l10n_ar_afip_service_start and self.l10n_ar_afip_service_end and self.invoice_date_due
        ):
            raise UserError(_('Para servicios, complete inicio/fin del servicio y fecha de vencimiento.'))

        currency = self.currency_id
        currency_code, rate = self._l10n_ar_currency_values()
        items = []
        vat_totals = {}
        taxed = untaxed = exempt = 0.0
        for line in lines:
            vat_codes = {
                (tax.tax_group_id.l10n_ar_vat_afip_code or '').strip()
                for tax in line.tax_ids
                if (tax.tax_group_id.l10n_ar_vat_afip_code or '').strip()
            }
            if len(vat_codes) != 1 or not vat_codes <= VAT_IDS:
                raise UserError(_('Cada línea WSMTXCA debe tener exactamente un IVA argentino reconocido.'))
            vat_code = vat_codes.pop()
            if any(not (tax.tax_group_id.l10n_ar_vat_afip_code or '').strip() for tax in line.tax_ids):
                raise UserError(_('WSMTXCA todavía no admite otros tributos por línea en esta versión.'))
            barcode = _digits(line.product_id.barcode)
            if not barcode:
                raise UserError(_('El producto %s necesita código de barras (GTIN) para WSMTXCA.') % line.product_id.display_name)
            uom_code = _digits(line.product_uom_id.l10n_ar_afip_code)
            if not uom_code:
                raise UserError(_('La unidad de medida %s no tiene código ARCA.') % line.product_uom_id.name)
            net = currency.round(line.price_subtotal)
            vat = currency.round(line.price_total - line.price_subtotal)
            gross = line.quantity * line.price_unit
            discount = currency.round(gross - line.price_subtotal) if not line.tax_ids.filtered('price_include') else 0.0
            if vat_code == '1':
                untaxed += net
            elif vat_code == '2':
                exempt += net
            else:
                taxed += net
                vat_totals[vat_code] = vat_totals.get(vat_code, 0.0) + vat
            unit_price = line.price_subtotal / line.quantity if line.quantity else 0.0
            if letter == 'B':
                unit_price = line.price_total / line.quantity if line.quantity else 0.0
            items.append({
                'unidadesMtx': f'{max(int(round(line.quantity)), 1)}',
                'codigoMtx': barcode,
                'codigo': (line.product_id.default_code or barcode)[:50],
                'descripcion': (line.name or line.product_id.display_name or '')[:4000],
                'cantidad': f'{line.quantity:.6f}',
                'codigoUnidadMedida': uom_code,
                'precioUnitario': f'{unit_price:.6f}',
                'importeBonificacion': f'{discount:.2f}',
                'codigoCondicionIVA': vat_code,
                'importeIVA': f'{vat:.2f}' if letter == 'A' and vat_code not in ('1', '2') else None,
                'importeItem': f'{currency.round(net + vat):.2f}',
            })
        vat_total = currency.round(sum(vat_totals.values()))
        subtotal = currency.round(taxed + untaxed + exempt)
        if currency.compare_amounts(subtotal, self.amount_untaxed):
            raise UserError(_('Las bases fiscales no coinciden con el neto de la factura.'))
        if currency.compare_amounts(currency.round(subtotal + vat_total), self.amount_total):
            raise UserError(_('Neto más IVA no coincide con el total de la factura.'))

        root = ET.Element(f'{{{SOAP_NS}}}Envelope')
        ET.register_namespace('ser', WSMTXCA_NS)
        body = ET.SubElement(root, f'{{{SOAP_NS}}}Body')
        operation = ET.SubElement(body, f'{{{WSMTXCA_NS}}}autorizarComprobanteRequest')

        def add(parent, tag, value=None):
            node = ET.SubElement(parent, tag)
            if value is not None:
                node.text = str(value)
            return node

        auth = add(operation, 'authRequest')
        add(auth, 'token', conn.token)
        add(auth, 'sign', conn.sign)
        add(auth, 'cuitRepresentada', cuit)
        cmp = add(operation, 'comprobanteCAERequest')
        for tag, value in (
            ('codigoTipoComprobante', document_code),
            ('numeroPuntoVenta', pos_number),
            ('numeroComprobante', number),
            ('fechaEmision', self.invoice_date.isoformat()),
            ('codigoTipoDocumento', doc_type),
            ('numeroDocumento', doc_number),
            ('importeGravado', f'{currency.round(taxed):.2f}'),
            ('importeNoGravado', f'{currency.round(untaxed):.2f}'),
            ('importeExento', f'{currency.round(exempt):.2f}'),
            ('importeSubtotal', f'{subtotal:.2f}'),
            ('importeTotal', f'{currency.round(self.amount_total):.2f}'),
            ('codigoMoneda', currency_code),
            ('cotizacionMoneda', f'{rate:.6f}'),
            ('codigoConcepto', concept),
        ):
            add(cmp, tag, value)
        if concept in ('2', '3'):
            add(cmp, 'fechaServicioDesde', self.l10n_ar_afip_service_start.isoformat())
            add(cmp, 'fechaServicioHasta', self.l10n_ar_afip_service_end.isoformat())
            add(cmp, 'fechaVencimientoPago', self.invoice_date_due.isoformat())
        associated = self._l10n_ar_associated_document()
        if document_type.internal_type in ('credit_note', 'debit_note'):
            if not associated or not associated.l10n_ar_afip_auth_code:
                raise UserError(_('La nota requiere un comprobante asociado autorizado.'))
            parts = associated._l10n_ar_get_document_number_parts(
                associated.l10n_latam_document_number, str(associated.l10n_latam_document_type_id.code),
            )
            assoc = add(add(cmp, 'arrayComprobantesAsociados'), 'comprobanteAsociado')
            add(assoc, 'codigoTipoComprobante', associated.l10n_latam_document_type_id.code)
            add(assoc, 'numeroPuntoVenta', associated.journal_id.l10n_ar_afip_pos_number)
            add(assoc, 'numeroComprobante', parts['invoice_number'])
        items_node = add(cmp, 'arrayItems')
        for item in items:
            item_node = add(items_node, 'item')
            for tag, value in item.items():
                if value is not None:
                    add(item_node, tag, value)
        if vat_totals:
            vat_node = add(cmp, 'arraySubtotalesIVA')
            for code in sorted(vat_totals, key=int):
                row = add(vat_node, 'subtotalIVA')
                add(row, 'codigo', code)
                add(row, 'importe', f'{currency.round(vat_totals[code]):.2f}')
        return ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')

    @staticmethod
    def _l10n_ar_wsmtxca_messages(root):
        messages = []
        for node in root.iter():
            if _local(node) != 'codigoDescripcion':
                continue
            values = {_local(child): (child.text or '').strip() for child in node}
            messages.append(f"{values.get('codigo', '')}: {values.get('descripcion', '')}"[:300])
        return messages[:5]

    def _l10n_ar_request_cae_wsmtxca(self, conn):
        self.ensure_one()
        req_xml = self._l10n_ar_build_wsmtxca_request_xml(conn)
        root = conn._ws_post_envelope(req_xml, 'wsmtxca', '', 'autorizarComprobante')
        result = next(((node.text or '').strip() for node in root.iter() if _local(node) == 'resultado'), '')
        cae = next(((node.text or '').strip() for node in root.iter() if _local(node) == 'CAE'), '')
        due = next(((node.text or '').strip() for node in root.iter() if _local(node) == 'fechaVencimientoCAE'), '')
        if result not in ('A', 'O') or not (cae.isdigit() and len(cae) == 14) or len(due) < 10:
            messages = self._l10n_ar_wsmtxca_messages(root)
            suffix = (' ' + '; '.join(messages)) if messages else ''
            raise UserError(_('ARCA no autorizó el comprobante con detalle. No se generó ningún CAE local.%s') % suffix)
        self._l10n_ar_store_authorization(
            cae, fields.Date.to_date(due[:10]), result, req_xml, ET.tostring(root, encoding='unicode'),
        )
