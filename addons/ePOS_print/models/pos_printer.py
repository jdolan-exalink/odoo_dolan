import os
import base64
import io
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    epos_print_protocol = fields.Selection(
        [('epson_epos', 'Epson ePOS'), ('escpos_bridge', 'ESC/POS por puente')],
        string='Protocolo de impresión', default='epson_epos', required=True,
        help='Las impresoras ESC/POS envían ePOS desde el navegador al puente; el puente las traduce y las entrega por TCP/IP.',
    )
    epos_print_device_host = fields.Char(
        string='Impresora de destino',
        help='IP de la impresora ESC/POS a la que el puente envía el trabajo. Informativo; el destino se autoriza en la configuración del puente.',
    )

    epos_print_last_test_state = fields.Selection(
        [('never', 'Sin probar'), ('ok', 'Disponible'), ('error', 'Error')],
        string='Estado de prueba', default='never', readonly=True, copy=False,
    )
    epos_print_last_test_at = fields.Datetime(string='Última prueba', readonly=True, copy=False)
    epos_print_last_test_message = fields.Char(string='Resultado de prueba', readonly=True, copy=False)

    def action_epos_print_test(self):
        self.ensure_one()
        if not self.env.user.has_group('point_of_sale.group_pos_manager'):
            raise AccessError(_('Solo un responsable de Punto de Venta puede probar impresoras.'))
        if self.printer_type != 'epson_epos' or not self.printer_ip:
            raise UserError(_('Configurá el endpoint ePOS de la impresora o del puente antes de probarla.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'epos_print_test',
            'name': _('Prueba de impresión'),
            'params': self._epos_print_test_params(),
        }

    def _epos_print_test_params(self):
        self.ensure_one()
        return {
            'printer_id': self.id,
            'name': self.name,
            'printer_ip': self.printer_ip,
            'use_lna': self.use_lna,
            'print_protocol': self.epos_print_protocol,
            'device_host': self.epos_print_device_host,
            'paper_size': self.paper_size,
            'use_type': self.use_type,
            'last_test_state': self.epos_print_last_test_state,
            'last_test_at': fields.Datetime.to_string(self.epos_print_last_test_at) if self.epos_print_last_test_at else '',
            'receipt_xml': self._epos_print_test_receipt_xml(),
        }

    def action_get_epos_print_test_params(self):
        self.ensure_one()
        if not self.env.user.has_group('point_of_sale.group_pos_manager'):
            raise AccessError(_('Solo un responsable de Punto de Venta puede probar impresoras.'))
        return self._epos_print_test_params()

    def _epos_print_test_receipt_xml(self):
        """Build a clearly marked demo ticket, including the active company's logo."""
        company = self.env.company
        logo_xml = ''
        if company.logo:
            try:
                from PIL import Image

                image = Image.open(io.BytesIO(base64.b64decode(company.logo))).convert('RGBA')
                white = Image.new('RGBA', image.size, (255, 255, 255, 255))
                white.alpha_composite(image)
                image = white.convert('L')
                image.thumbnail((384, 128))
                image = image.point(lambda value: 0 if value < 165 else 255, mode='1')
                width, height = image.size
                pixels = image.load()
                packed = bytearray()
                for y in range(height):
                    for byte_x in range((width + 7) // 8):
                        value = 0
                        for bit in range(8):
                            x = byte_x * 8 + bit
                            if x < width and pixels[x, y] == 0:
                                value |= 1 << (7 - bit)
                        packed.append(value)
                logo_xml = (
                    f'<image align="center" width="{width}" height="{height}" '
                    f'mode="mono">{base64.b64encode(packed).decode("ascii")}</image>'
                )
            except Exception:
                # A missing/unsupported logo must not prevent printing a test ticket.
                logo_xml = ''

        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        lines = [
            (company.name or 'Odoo ERP', 'center', True),
            ('TICKET DE PRUEBA', 'center', True),
            ('*** SIN VALOR FISCAL ***', 'center', True),
            ('--------------------------------', 'center', False),
            ('1 x Abono de mantenimiento demo', 'left', False),
            ('$ 12.500,00', 'right', False),
            ('1 x Accesorio de red demo', 'left', False),
            ('$ 3.250,00', 'right', False),
            ('1 x Cableado demo', 'left', False),
            ('$ 1.990,00', 'right', False),
            ('--------------------------------', 'center', False),
            ('TOTAL DEMO: $ 17.740,00', 'right', True),
            (now.strftime('%d/%m/%Y %H:%M'), 'center', False),
            ('No genera venta ni comprobante', 'center', False),
        ]
        text_xml = ''.join(
            f'<text align="{align}" bold="{str(bold).lower()}">{escape(text)}</text>'
            for text, align, bold in lines
        )
        return (
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'
            f'{logo_xml}{text_xml}<feed line="1"/><cut type="feed"/>'
            '</epos-print></s:Body></s:Envelope>'
        )

    def action_record_epos_print_test(self, state, message=''):
        self.ensure_one()
        if not self.env.user.has_group('point_of_sale.group_pos_manager'):
            raise AccessError(_('Solo un responsable de Punto de Venta puede registrar una prueba.'))
        if state not in ('ok', 'error'):
            raise UserError(_('El resultado de prueba no es válido.'))
        self.write({
            'epos_print_last_test_state': state,
            'epos_print_last_test_at': fields.Datetime.now(),
            'epos_print_last_test_message': str(message or '')[:255],
        })
        return True

    def action_epos_print_bridge_test(self):
        self.ensure_one()
        if not self.env.user.has_group('point_of_sale.group_pos_manager'):
            raise AccessError(_('Solo un responsable de Punto de Venta puede probar impresoras.'))
        if self.epos_print_protocol != 'escpos_bridge':
            raise UserError(_('Esta prueba de servidor solo corresponde a impresoras ESC/POS por puente.'))

        bridge_url = os.environ.get('EPOS_BRIDGE_INTERNAL_URL', 'http://escpos_bridge:8765').rstrip('/')
        receipt = self._epos_print_test_receipt_xml().encode('utf-8')
        origin = request.httprequest.host_url.rstrip('/') if request else ''
        req = urllib.request.Request(
            f'{bridge_url}/cgi-bin/epos/service.cgi?devid=local_printer',
            data=receipt,
            headers={
                'Content-Type': 'text/xml',
                'Origin': origin,
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read()
            result = next(
                (node for node in ET.fromstring(body).iter() if node.tag.rsplit('}', 1)[-1] == 'response'),
                None,
            )
            if result is None or result.attrib.get('success') != 'true' or result.attrib.get('code'):
                raise UserError(_('El puente rechazó la impresión: %s') % (result.attrib.get('code', 'respuesta inválida') if result is not None else 'respuesta inválida'))
        except urllib.error.URLError as exc:
            reason = getattr(exc, 'reason', exc)
            raise UserError(_('No se pudo contactar el puente ESC/POS (%s).') % reason) from exc
        except ET.ParseError as exc:
            raise UserError(_('El puente devolvió una respuesta inválida.')) from exc

        self.action_record_epos_print_test('ok', _('La impresora aceptó el trabajo desde el servidor.'))
        return {'success': True}
