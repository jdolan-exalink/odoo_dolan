# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
"""Cliente del servicio COT (Código de Operación de Traslado) de ARBA.

El archivo TB_ tiene registros separados por ``|``:

- 01: cabecera con la CUIT de la empresa.
- 02: un registro por remito (fechas, código único, destinatario, domicilios,
  transporte e importe).
- 03: productos del remito (código nomenclador, unidad ARBA, cantidad).
- 04: pie con la cantidad de remitos.

El diseño de registro se arma en ``build_file``; validarlo con el ambiente de
homologación de ARBA antes de pasar a producción.
"""
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

COT_URLS = {
    'test': 'https://cot.test.arba.gov.ar/TransporteBienes/SeguridadCliente/presentarRemitos.do',
    'prod': 'https://cot.arba.gov.ar/TransporteBienes/SeguridadCliente/presentarRemitos.do',
}
TIMEOUT = 60


def clean(value, size=None):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[|\r\n]+', ' ', text).strip()
    return text[:size] if size else text


def digits(value):
    return re.sub(r'\D', '', str(value or ''))


def split_street(street):
    """'Av. Siempre Viva 742' -> ('Av. Siempre Viva', '742')."""
    match = re.match(r'^(.*?)[\s,]+(\d+)\s*$', (street or '').strip())
    if match:
        return match.group(1), match.group(2)
    return street or '', 'S/N'


class DolanCotService(models.AbstractModel):
    _name = 'dolan.cot.service'
    _description = 'Servicio COT de ARBA'

    # ------------------------------------------------------------------
    # Construcción del archivo
    # ------------------------------------------------------------------
    @api.model
    def _address_fields(self, partner):
        street, number = split_street(partner.street)
        return [
            clean(street, 40), clean(number, 5), '', '', '',
            clean(partner.street2, 30), clean(partner.zip, 8).replace(' ', '').upper(),
            clean(partner.city, 50), clean(partner.state_id.code, 1),
        ]

    @api.model
    def _remito_record(self, picking):
        company = picking.company_id
        partner = picking.partner_id
        commercial = partner.commercial_partner_id
        origin = picking.picking_type_id.warehouse_id.partner_id or company.partner_id
        departure = fields.Datetime.context_timestamp(picking, picking.dolan_cot_departure or fields.Datetime.now())
        emission = picking.date_done or picking.scheduled_date or fields.Datetime.now()
        emission = fields.Datetime.context_timestamp(picking, emission)
        final_consumer = commercial.l10n_ar_afip_responsibility_type_id.code == '5'
        cuit = digits(commercial.vat) if not final_consumer else ''
        doc_type = 'DNI' if final_consumer else ''
        doc_number = digits(commercial.vat) if final_consumer else ''
        carrier = picking.dolan_cot_carrier_id
        values = [
            '02',
            emission.strftime('%Y%m%d'),
            picking._dolan_cot_unique_code(),
            departure.strftime('%Y%m%d'),
            departure.strftime('%H%M'),
            'E',  # sujeto generador: emisor
            '1' if final_consumer else '0',
            doc_type,
            doc_number,
            cuit,
            clean(commercial.name, 50),
            '0',  # destinatario tenedor
            *self._address_fields(partner),
            '',  # código de domicilio propio del destino
            'NO',  # entrega en domicilio de origen
            digits(company.vat),
            clean(company.name, 50),
            '0',  # emisor tenedor
            *self._address_fields(origin),
            digits(carrier.vat) if carrier else '',
            picking.dolan_cot_route_type or '',
            '', '', '',  # recorrido: localidad, calle, ruta
            clean(picking.dolan_cot_vehicle_plate).replace(' ', '').upper()[:7],
            clean(picking.dolan_cot_trailer_plate).replace(' ', '').upper()[:7],
            '0',  # producto no terminado / devolución
            '%.2f' % picking.dolan_cot_amount,
        ]
        return '|'.join(values)

    @api.model
    def _product_records(self, picking):
        records = []
        missing = []
        for move in picking.move_ids.filtered(lambda m: m.state != 'cancel' and m.quantity):
            product = move.product_id
            code = digits(product.product_tmpl_id.dolan_cot_code)
            uom_code = move.uom_id.dolan_cot_uom_code
            if not code or not uom_code:
                missing.append(product.display_name)
                continue
            records.append('|'.join([
                '03',
                code[:6].ljust(6, '0'),
                uom_code,
                '%.2f' % move.quantity,
                clean(product.default_code, 25),
                clean(product.name, 40),
                clean(move.uom_id.name, 20),
                '%.2f' % move.quantity,
            ]))
        if missing:
            raise UserError(_(
                'Faltan el código nomenclador COT o la unidad ARBA en estos productos del remito %(name)s:\n%(products)s',
                name=picking.name, products='\n'.join(missing)))
        return records

    @api.model
    def build_file(self, pickings):
        """Devuelve (nombre_de_archivo, contenido) para presentar en ARBA."""
        company = pickings.company_id
        if len(company) != 1:
            raise UserError(_('Los remitos de un mismo archivo COT deben ser de una sola compañía.'))
        if not digits(company.vat):
            raise UserError(_('La compañía no tiene CUIT.'))
        lines = ['01|%s' % digits(company.vat)]
        for picking in pickings:
            picking._dolan_cot_check_ready()
            lines.append(self._remito_record(picking))
            lines.extend(self._product_records(picking))
        lines.append('04|%s' % len(pickings))
        company.sudo().dolan_cot_file_sequence += 1
        today = fields.Date.context_today(self).strftime('%Y%m%d')
        filename = 'TB_%s_%s_%s_%06d.txt' % (
            digits(company.vat), digits(company.dolan_cot_plant).rjust(6, '0')[-6:], today,
            company.sudo().dolan_cot_file_sequence)
        return filename, '\r\n'.join(lines) + '\r\n'

    # ------------------------------------------------------------------
    # Envío y respuesta
    # ------------------------------------------------------------------
    @api.model
    def _post(self, company, filename, content):
        """POST multipart al servicio de ARBA. Devuelve el XML de respuesta."""
        company = company.sudo()
        if not company.dolan_cot_user or not company.dolan_cot_password:
            raise UserError(_('Configurá el usuario y la clave CIT del COT en la compañía.'))
        url = COT_URLS[company.dolan_cot_environment or 'test']
        try:
            response = requests.post(url, data={
                'user': digits(company.dolan_cot_user),
                'password': company.dolan_cot_password,
            }, files={'file': (filename, content.encode('latin-1', errors='replace'), 'text/plain')},
                timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.warning('COT ARBA: error de comunicación: %s', exc)
            raise UserError(_('No se pudo comunicar con ARBA: %s', exc)) from exc
        return response.content

    @api.model
    def parse_response(self, payload):
        """Interpreta la respuesta de ARBA.

        Devuelve ``{'cots': {codigo_unico: cot}, 'errors': {codigo_unico|'': [mensajes]}}``.
        """
        result = {'cots': {}, 'errors': {}}
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            result['errors'][''] = [_('Respuesta de ARBA ilegible: %s', clean(payload[:300]))]
            return result

        def text(node, *names):
            for name in names:
                child = node.find('.//%s' % name)
                if child is not None and child.text:
                    return child.text.strip()
            return ''

        for error in root.iter('TBError'):
            result['errors'].setdefault('', []).append(
                '%s %s' % (text(error, 'codigoError'), text(error, 'mensajeError')))
        for remito in root.iter('remito'):
            code = text(remito, 'numeroUnico')
            cot = text(remito, 'cot', 'COT', 'codigoIntegridad')
            processed = text(remito, 'procesado').upper()
            messages = [('%s %s' % (text(err, 'codigoError'), text(err, 'mensajeError'))).strip()
                        for err in remito.iter('error')]
            if cot and processed != 'NO':
                result['cots'][code] = cot
            else:
                result['errors'].setdefault(code, []).extend(messages or [_('ARBA no devolvió COT.')])
        return result

    @api.model
    def request_cot(self, pickings):
        filename, content = self.build_file(pickings)
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'raw': content.encode('latin-1', errors='replace'),
            'mimetype': 'text/plain',
            'res_model': 'stock.picking',
            'res_id': pickings[:1].id,
        })
        payload = self._post(pickings.company_id, filename, content)
        result = self.parse_response(payload)
        general = result['errors'].get('', [])
        now = fields.Datetime.now()
        for picking in pickings:
            code = picking._dolan_cot_unique_code()
            vals = {'dolan_cot_file_id': attachment.id, 'dolan_cot_date': now}
            if code in result['cots']:
                vals.update(dolan_cot_number=result['cots'][code], dolan_cot_state='done', dolan_cot_message=False)
            else:
                messages = result['errors'].get(code, []) + general
                vals.update(dolan_cot_state='error',
                            dolan_cot_message='\n'.join(messages) or _('ARBA no devolvió COT para este remito.'))
            picking.write(vals)
            picking.message_post(body=_('COT ARBA: %s', vals.get('dolan_cot_number') or vals['dolan_cot_message']))
        return result
