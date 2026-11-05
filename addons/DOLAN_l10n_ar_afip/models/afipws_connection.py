# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import base64
import logging
import ssl
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

WSAA_URLS = {
    'testing': 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms',
    'production': 'https://wsaa.afip.gov.ar/ws/services/LoginCms',
}

AFIP_WS_URLS = {
    'testing': {
        'wsfe': 'https://wswhomo.afip.gov.ar/wsfev1/service.asmx',
        'wsfex': 'https://wswhomo.afip.gov.ar/wsfexv1/service.asmx',
        'wsmtxca': 'https://fwshomo.afip.gov.ar/wsmtxca/services/MTXCAService',
        'ws_sr_constancia_inscripcion': 'https://awshomo.arca.gob.ar/sr-padron/webservices/personaServiceA5',
    },
    'production': {
        'wsfe': 'https://servicios1.afip.gov.ar/wsfev1/service.asmx',
        'wsfex': 'https://servicios1.afip.gov.ar/wsfexv1/service.asmx',
        'wsmtxca': 'https://serviciosjava.afip.gov.ar/wsmtxca/services/MTXCAService',
        'ws_sr_constancia_inscripcion': 'https://aws.arca.gob.ar/sr-padron/webservices/personaServiceA5',
    },
}


class L10nArAfipwsConnection(models.Model):
    _name = 'l10n_ar.afipws.connection'
    _description = 'Conexión Webservice ARCA/AFIP (Ticket de Acceso WSAA)'
    _order = 'expiration_time desc, id desc'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete='cascade',
    )
    l10n_ar_afip_ws = fields.Selection(
        selection=[
            ('wsfe', 'Mercado interno -sin detalle- RG2485 (WSFEv1)'),
            ('wsfex', 'Exportación -con detalle- RG2758 (WSFEXv1)'),
            ('wsmtxca', 'Mercado interno -con detalle- RG2904 (WSMTXCA)'),
            ('ws_sr_constancia_inscripcion', 'Consulta de Padrón Constancia de Inscripción (A5)'),
        ],
        string='Webservice ARCA/AFIP',
        required=True,
        default='wsfe',
        index=True,
    )
    type = fields.Selection(
        selection=[
            ('production', 'Producción'),
            ('testing', 'Homologación (Testing)'),
        ],
        string='Ambiente',
        required=True,
        default='testing',
        index=True,
    )
    uniqueid = fields.Char(
        string='Unique ID',
        readonly=True,
        help='Identificador único del Ticket de Requerimiento de Acceso (TRA).',
    )
    generation_time = fields.Datetime(
        string='Fecha de Generación',
        readonly=True,
    )
    expiration_time = fields.Datetime(
        string='Fecha de Expiración',
        readonly=True,
    )
    token = fields.Text(
        string='Token',
        readonly=True,
    )
    sign = fields.Text(
        string='Sign',
        readonly=True,
    )
    is_simulated = fields.Boolean(
        string='Modo Simulación Homologación',
        readonly=True,
        default=False,
    )

    @api.depends('company_id', 'l10n_ar_afip_ws', 'type', 'expiration_time')
    def _compute_display_name(self):
        for rec in self:
            ws_label = dict(self._fields['l10n_ar_afip_ws'].selection).get(rec.l10n_ar_afip_ws, rec.l10n_ar_afip_ws)
            rec.display_name = f"{rec.company_id.name} - {ws_label} ({rec.type})"

    def _is_valid(self):
        self.ensure_one()
        now = fields.Datetime.now()
        return bool(self.token and self.sign and self.expiration_time and self.expiration_time > now)

    def _build_tra_xml(self, service_name):
        """Construye el XML de Ticket de Requerimiento de Acceso (TRA) para WSAA."""
        tz_ar = timezone(timedelta(hours=-3))
        now_ar = datetime.now(tz_ar)
        gen_time = (now_ar - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S-03:00')
        exp_time = (now_ar + timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S-03:00')
        unique_id = str(int(time.time()))
        tra_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<loginTicketRequest version="1.0">'
            '<header>'
            f'<uniqueId>{unique_id}</uniqueId>'
            f'<generationTime>{gen_time}</generationTime>'
            f'<expirationTime>{exp_time}</expirationTime>'
            '</header>'
            f'<service>{service_name}</service>'
            '</loginTicketRequest>'
        )
        return tra_xml, unique_id

    def _sign_tra_cms(self, tra_xml, cert_pem, key_pem):
        """Firma el TRA XML en formato CMS (PKCS#7) Base64 usando cryptography, pyafipws u OpenSSL."""

        def pem_text(value):
            # Odoo 20 returns BinaryValue objects for Binary fields, while older
            # releases exposed raw bytes. Read their content before stringifying.
            content = getattr(value, 'content', None)
            if content is not None:
                value = content
            if isinstance(value, str):
                raw = value.encode('utf-8')
            elif isinstance(value, (bytes, bytearray, memoryview)):
                raw = bytes(value)
            else:
                raw = str(value or '').encode('utf-8')
            if b'-----BEGIN' in raw:
                return raw.decode('utf-8', errors='ignore')
            try:
                decoded = base64.b64decode(raw, validate=True)
                if b'-----BEGIN' in decoded:
                    return decoded.decode('utf-8', errors='ignore')
            except Exception:
                pass
            return raw.decode('utf-8', errors='ignore')

        cert_str = pem_text(cert_pem)
        key_str = pem_text(key_pem)

        # Si el contenido está en base64 sin encabezados PEM, decodificarlo primero
        if '-----BEGIN' not in cert_str:
            try:
                decoded = base64.b64decode(cert_str).decode('utf-8', errors='ignore')
                if '-----BEGIN' in decoded:
                    cert_str = decoded
            except Exception:
                pass
        if '-----BEGIN' not in key_str:
            try:
                decoded_k = base64.b64decode(key_str).decode('utf-8', errors='ignore')
                if '-----BEGIN' in decoded_k:
                    key_str = decoded_k
            except Exception:
                pass

        # Intento 1: cryptography hazmat pkcs7 (estándar en Python 3.12)
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.serialization import pkcs7

            cert_obj = x509.load_pem_x509_certificate(cert_str.encode('utf-8'))
            key_obj = serialization.load_pem_private_key(key_str.encode('utf-8'), password=None)
            cms_der = (
                pkcs7.PKCS7SignatureBuilder()
                .set_data(tra_xml.encode('utf-8'))
                .add_signer(cert_obj, key_obj, hashes.SHA256())
                .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
            )
            return base64.b64encode(cms_der).decode('ascii')
        except Exception as exc:
            _logger.debug("Firma CMS con cryptography falló (%s), probando pyafipws...", exc)

        # Intento 2: pyafipws wsaa
        try:
            from pyafipws.wsaa import WSAA
            wsaa = WSAA()
            cms = wsaa.CreateTRA(service=self.l10n_ar_afip_ws, ttl=36000)
            signed = wsaa.SignTRA(cms, cert_str, key_str)
            return signed
        except Exception as exc:
            _logger.warning("No se pudo firmar TRA con pyafipws: %s", exc)
            raise UserError(_(
                "No se pudo firmar el Ticket de Acceso (TRA) con el certificado X.509 configurado.\n"
                "Verifique que el certificado y la clave privada estén en formato PEM válido.\nDetalle: %s"
            ) % exc)

    def _call_wsaa_soap(self, cms_b64, environment):
        """Invoca el servicio SOAP LoginCms de WSAA y parsea el LoginTicketResponse."""
        url = WSAA_URLS.get(environment, WSAA_URLS['testing'])
        soap_envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
   <soapenv:Header/>
   <soapenv:Body>
      <wsaa:loginCms>
         <wsaa:in0>{cms_b64}</wsaa:in0>
      </wsaa:loginCms>
   </soapenv:Body>
</soapenv:Envelope>"""
        req = urllib.request.Request(
            url,
            data=soap_envelope.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': '""',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw_xml = response.read().decode('utf-8')
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode('utf-8', errors='ignore')
            raise UserError(_("Error HTTP de WSAA ARCA/AFIP (%s): %s") % (http_err.code, err_body))
        except Exception as exc:
            raise UserError(_("No se pudo conectar con WSAA ARCA/AFIP (%s): %s") % (url, exc))

        root = ET.fromstring(raw_xml)
        login_return = None
        for elem in root.iter():
            if elem.tag.endswith('loginCmsReturn'):
                login_return = elem.text
                break
        if not login_return:
            raise UserError(_("Respuesta inesperada de WSAA ARCA/AFIP: %s") % raw_xml[:500])

        ltr_root = ET.fromstring(login_return)
        unique_id = ltr_root.findtext('.//header/uniqueId') or ''
        token = ltr_root.findtext('.//credentials/token') or ''
        sign = ltr_root.findtext('.//credentials/sign') or ''
        return {
            'uniqueid': unique_id,
            'token': token,
            'sign': sign,
            'generation_time': fields.Datetime.now(),
            'expiration_time': fields.Datetime.now() + timedelta(hours=11, minutes=50),
        }

    def action_renew_token(self):
        """Renueva un ticket real WSAA; la ausencia de credenciales es un error explícito."""
        for rec in self:
            company = rec.company_id
            # Certificate records intentionally require administrator access.
            # Read their signing material server-side for the connection's own
            # company; never grant ordinary accounting users access to private
            # key or certificate binary fields.
            credential_company = company.sudo()
            shared_padron = False
            if rec.l10n_ar_afip_ws == 'ws_sr_constancia_inscripcion':
                shared_padron = self.env['res.config.settings']._get_dolan_padron_configuration()
            if shared_padron:
                cert_rec = shared_padron['certificate']
                key_rec = shared_padron['key']
            else:
                cert_rec = credential_company.l10n_ar_afip_ws_crt_id
                key_rec = credential_company.l10n_ar_afip_ws_key_id

            if cert_rec and key_rec:
                cert_rec = cert_rec.sudo()
                key_rec = key_rec.sudo()
                if not shared_padron and cert_rec.company_id and cert_rec.company_id != company:
                    raise UserError(_('El certificado ARCA configurado no pertenece a la compañía de la conexión.'))
                if not shared_padron and key_rec.company_id and key_rec.company_id != company:
                    raise UserError(_('La clave ARCA configurada no pertenece a la compañía de la conexión.'))
                cert_pem = getattr(cert_rec, 'pem_certificate', None) or getattr(cert_rec, 'content', None)
                key_pem = getattr(key_rec, 'pem_key', None) or getattr(key_rec, 'content', None)
                if cert_pem and key_pem:
                    tra_xml, unique_id = rec._build_tra_xml(rec.l10n_ar_afip_ws)
                    cms_b64 = rec._sign_tra_cms(tra_xml, cert_pem, key_pem)
                    ta_vals = rec._call_wsaa_soap(cms_b64, rec.type)
                    ta_vals['is_simulated'] = False
                    rec.write(ta_vals)
                    continue

            raise UserError(_(
                'Para autenticar en ARCA debe configurar certificado y clave privada '
                'autorizados para el ambiente seleccionado. Las pruebas sin credenciales '
                'usan mocks de la suite y no generan tickets ni autorizaciones fiscales.'
            ))
        return True

    @api.model
    def get_active_connection(self, company, afip_ws='wsfe'):
        """Obtiene una conexión activa o crea/renueva una para la compañía y webservice indicados."""
        env_type = company.l10n_ar_afip_ws_environment or 'testing'
        conn = self.search([
            ('company_id', '=', company.id),
            ('l10n_ar_afip_ws', '=', afip_ws),
            ('type', '=', env_type),
        ], limit=1)
        if not conn:
            conn = self.create({
                'company_id': company.id,
                'l10n_ar_afip_ws': afip_ws,
                'type': env_type,
            })
        if not conn._is_valid():
            conn.action_renew_token()
        return conn

    def _call_wsfe_query(self, method, values):
        """Read-only WSFE query. No local invoice can substitute an ARCA response."""
        self.ensure_one()
        supported_methods = {
            'FECompUltimoAutorizado': 'FECompUltimoAutorizado',
            'FECompConsultar': 'FECompConsultar',
            'FEParamGetTiposTributos': 'FEParamGetTiposTributos',
            'FEParamGetCondicionIvaReceptor': 'FEParamGetCondicionIvaReceptor',
        }
        if method not in supported_methods:
            raise UserError(_('Consulta WSFE no soportada.'))
        if self.is_simulated or self.l10n_ar_afip_ws != 'wsfe':
            raise UserError(_('La consulta requiere un ticket real del servicio WSFE.'))
        cuit = ''.join(ch for ch in (self.company_id.vat or '') if ch.isdigit())
        if len(cuit) != 11:
            raise UserError(_('Configure el CUIT emisor antes de consultar ARCA.'))
        soap_ns = 'http://schemas.xmlsoap.org/soap/envelope/'
        ns = 'http://ar.gov.afip.dif.FEV1/'
        envelope = ET.Element(f'{{{soap_ns}}}Envelope')
        body = ET.SubElement(envelope, f'{{{soap_ns}}}Body')
        operation = ET.SubElement(body, f'{{{ns}}}{supported_methods[method]}')
        auth = ET.SubElement(operation, f'{{{ns}}}Auth')
        for key, value in (('Token', self.token), ('Sign', self.sign), ('Cuit', cuit)):
            ET.SubElement(auth, f'{{{ns}}}{key}').text = str(value)
        parent = ET.SubElement(operation, f'{{{ns}}}FeCompConsReq') if method == 'FECompConsultar' else operation
        for key, value in values.items():
            ET.SubElement(parent, f'{{{ns}}}{key}').text = str(value)
        request = urllib.request.Request(
            AFIP_WS_URLS[self.type]['wsfe'],
            data=ET.tostring(envelope, encoding='utf-8', xml_declaration=True),
            headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': f'"{ns}{method}"'},
            method='POST',
        )
        try:
            ssl_context = ssl.create_default_context()
            # ARCA's production WSFE endpoint currently negotiates a DH group
            # below OpenSSL 3's default level 2. Keep peer/hostname validation
            # enabled and TLS 1.2+ mandatory, lowering only the DH security
            # threshold for this endpoint while retaining strong ciphers.
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.set_ciphers('HIGH:!aNULL:!MD5:@SECLEVEL=1')
            with urllib.request.urlopen(request, timeout=25, context=ssl_context) as response:
                root = ET.fromstring(response.read())
        except Exception as exc:
            raise UserError(_('No se pudo consultar ARCA (%s). No se sustituyó la respuesta con datos locales.') % type(exc).__name__) from exc
        fault = next((node for node in root.iter() if node.tag.split('}')[-1] == 'Fault'), None)
        if fault is not None:
            fault_message = next((
                (node.text or '').strip()
                for node in fault.iter()
                if node.tag.split('}')[-1] in ('faultstring', 'Text') and (node.text or '').strip()
            ), '')
            if fault_message:
                raise UserError(_('ARCA rechazó la consulta WSFE: %s') % fault_message[:400])
            raise UserError(_('ARCA devolvió un error SOAP sin detalle. Revise ambiente, servicio y credenciales WSAA.'))
        errors = [node for node in root.iter() if node.tag.split('}')[-1] == 'Err']
        if errors:
            messages = []
            for error in errors[:5]:
                values = {child.tag.split('}')[-1]: (child.text or '').strip() for child in error}
                code = values.get('Code', '')
                message = values.get('Msg', '')
                if code or message:
                    messages.append(f'{code}: {message}' if code and message else (code or message))
            detail = '; '.join(messages)[:800]
            if detail:
                raise UserError(_('ARCA rechazó la consulta WSFE (%s).') % detail)
            raise UserError(_('ARCA devolvió un error de consulta sin código ni descripción.'))
        result = next((node for node in root.iter() if node.tag.split('}')[-1] == method + 'Result'), None)
        if result is None:
            raise UserError(_('La respuesta ARCA no contiene el resultado solicitado.'))
        if method == 'FEParamGetCondicionIvaReceptor':
            conditions = [node for node in result.iter() if node.tag.split('}')[-1] == 'CondicionIvaReceptor']
            if not conditions:
                raise UserError(_('ARCA no devolvió condiciones IVA del receptor para la clase solicitada.'))
            for condition in conditions:
                values_by_name = {child.tag.split('}')[-1]: (child.text or '').strip() for child in condition}
                if not values_by_name.get('Id', '').isdigit() or not values_by_name.get('Desc') or not values_by_name.get('Cmp_Clase'):
                    raise UserError(_('ARCA devolvió una condición IVA incompleta.'))
        return result

    def _call_padron_get_person(self, cuit, represented_cuit=None):
        """Read one taxpayer from ARCA's authenticated ws_sr_constancia_inscripcion service."""
        self.ensure_one()
        if self.is_simulated or self.l10n_ar_afip_ws != 'ws_sr_constancia_inscripcion':
            raise UserError(_('La consulta de Padrón requiere un ticket real del servicio correspondiente.'))
        if not self._is_valid():
            raise UserError(_('El ticket de Padrón venció. Renueve la conexión antes de consultar.'))

        def normalize_cuit(value):
            digits = ''.join(char for char in (value or '') if char.isdigit())
            if len(digits) != 11:
                return ''
            weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
            remainder = 11 - sum(int(digits[index]) * weights[index] for index in range(10)) % 11
            check_digit = 0 if remainder == 11 else (9 if remainder == 10 else remainder)
            return digits if check_digit == int(digits[10]) else ''

        target_cuit = normalize_cuit(cuit)
        represented_cuit = normalize_cuit(represented_cuit or self.company_id.vat)
        if not target_cuit:
            raise UserError(_('El CUIT consultado no tiene formato o dígito verificador válido.'))
        if not represented_cuit:
            raise UserError(_('Configure un CUIT válido en la compañía que representa la consulta.'))
        if not self.token or not self.sign:
            raise UserError(_('El ticket de Padrón no contiene credenciales válidas.'))

        soap_env = 'http://schemas.xmlsoap.org/soap/envelope/'
        padron_ns = 'http://a5.soap.ws.server.puc.sr/'
        envelope = ET.Element(f'{{{soap_env}}}Envelope')
        ET.SubElement(envelope, f'{{{soap_env}}}Header')
        body = ET.SubElement(envelope, f'{{{soap_env}}}Body')
        operation = ET.SubElement(body, f'{{{padron_ns}}}getPersona_v2')
        for name, value in (
            ('token', self.token),
            ('sign', self.sign),
            ('cuitRepresentada', represented_cuit),
            ('idPersona', target_cuit),
        ):
            ET.SubElement(operation, name).text = value
        request = urllib.request.Request(
            AFIP_WS_URLS[self.type]['ws_sr_constancia_inscripcion'],
            data=ET.tostring(envelope, encoding='utf-8', xml_declaration=True),
            headers={'Content-Type': 'text/xml; charset=utf-8'},
            method='POST',
        )
        ssl_context = ssl.create_default_context()
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            with urllib.request.urlopen(request, timeout=25, context=ssl_context) as response:
                raw_xml = response.read()
        except urllib.error.HTTPError as http_error:
            # Do not expose ARCA's full response: it can contain taxpayer data.
            raise UserError(_('ARCA rechazó la consulta de Padrón (HTTP %s).') % http_error.code)
        except Exception as exc:
            raise UserError(_('No se pudo conectar con el Padrón ARCA (%s).') % type(exc).__name__)

        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            raise UserError(_('ARCA devolvió una respuesta SOAP inválida para la consulta de Padrón.'))

        def local_name(element):
            return element.tag.rsplit('}', 1)[-1]

        fault = next((node for node in root.iter() if local_name(node) == 'Fault'), None)
        if fault is not None:
            fault_text = next((child.text for child in fault.iter() if local_name(child) in ('faultstring', 'Text') and child.text), '')
            raise UserError(_('ARCA informó un error en la consulta de Padrón%s.') % (': ' + fault_text[:250] if fault_text else '.'))
        person_return = next((node for node in root.iter() if local_name(node) == 'personaReturn'), None)
        if person_return is None:
            raise UserError(_('ARCA no devolvió datos de Padrón para el CUIT solicitado.'))
        error_node = next((node for node in person_return.iter() if local_name(node) == 'errorConstancia'), None)
        if error_node is not None:
            error_text = next((child.text for child in error_node.iter() if local_name(child) == 'error' and child.text), '')
            raise UserError(_('ARCA no pudo emitir la constancia para el CUIT solicitado%s.') % (': ' + error_text[:250] if error_text else '.'))
        general = next((node for node in person_return if local_name(node) == 'datosGenerales'), None)
        returned_cuit = next((child.text for child in general if local_name(child) == 'idPersona'), '') if general is not None else ''
        if general is None or normalize_cuit(returned_cuit) != target_cuit:
            raise UserError(_('La respuesta del Padrón no identifica al CUIT consultado. No se actualizaron datos locales.'))
        return person_return
