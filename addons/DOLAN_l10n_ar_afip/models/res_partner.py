# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """Keep IAP autocomplete off the contact's name/CUIT fields.

        When partner_autocomplete is installed, it injects paid IAP widgets into
        these fields at view-render time. DOLAN uses the authenticated ARCA
        Padron action instead, so typing does not trigger paid requests.
        """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            for node in arch.xpath("//field[@name='name' or @name='vat']"):
                if node.get('widget') == 'field_partner_autocomplete':
                    node.attrib.pop('widget', None)
        return arch, view

    l10n_ar_padron_last_update = fields.Datetime(
        string='Última Actualización Padrón ARCA',
        readonly=True,
        copy=False,
    )
    l10n_ar_padron_status = fields.Char(
        string='Estado en Padrón ARCA',
        readonly=True,
        copy=False,
    )
    l10n_ar_padron_error = fields.Char(
        string='Último error de consulta Padrón',
        readonly=True,
        copy=False,
    )

    def _l10n_ar_validate_cuit_checksum(self, cuit):
        """Valida el dígito verificador módulo 11 de una CUIT/CUIL argentina de 11 dígitos."""
        if not cuit or len(cuit) != 11 or not cuit.isdigit():
            return False
        weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(cuit[index]) * weights[index] for index in range(10))
        remainder = 11 - (total % 11)
        check = 0 if remainder == 11 else (9 if remainder == 10 else remainder)
        return check == int(cuit[10])

    def _l10n_ar_fetch_padron_data(self, cuit):
        self.ensure_one()
        settings = self.env['res.config.settings']
        shared = settings._get_dolan_padron_configuration()
        connection_company = shared['representative_company'] if shared else self.env.company
        connection = self.env['l10n_ar.afipws.connection'].get_active_connection(
            connection_company, 'ws_sr_constancia_inscripcion'
        )
        person = connection._call_padron_get_person(
            cuit,
            represented_cuit=shared['represented_cuit'] if shared else None,
        )
        return self._l10n_ar_parse_padron_person(person)

    def _l10n_ar_padron_partner_vals(self, data):
        self.ensure_one()
        vals = {
            'l10n_ar_padron_last_update': fields.Datetime.now(),
            'l10n_ar_padron_status': data.get('estadoClave') or (_('Con observaciones') if data.get('warnings') else False),
            'l10n_ar_padron_error': (
                _('Aviso de ARCA: %s') % ' | '.join(data['warnings'])
            )[:500] if data.get('warnings') else False,
        }
        if data.get('name'):
            vals['name'] = data['name']
        if data.get('direccion'):
            vals['street'] = data['direccion']
        if data.get('localidad'):
            vals['city'] = data['localidad']
        if data.get('codPostal'):
            vals['zip'] = data['codPostal']

        ar_country = self.env.ref('base.ar', raise_if_not_found=False)
        if ar_country:
            vals['country_id'] = ar_country.id
            provincia = data.get('provincia')
            if provincia:
                normalized_province = ''.join(
                    char for char in unicodedata.normalize('NFKD', provincia).casefold()
                    if not unicodedata.combining(char)
                ).strip()
                province_code_aliases = {
                    'ciudad autonoma buenos aires': 'C',
                    'caba': 'C',
                    'capital federal': 'C',
                }
                province_state = self.env['res.country.state']
                if normalized_province in province_code_aliases:
                    matches = province_state.search([
                        ('country_id', '=', ar_country.id),
                        ('code', '=', province_code_aliases[normalized_province]),
                    ], limit=2)
                else:
                    country_states = province_state.search([('country_id', '=', ar_country.id)])
                    matches = country_states.filtered(lambda state: ''.join(
                        char for char in unicodedata.normalize('NFKD', state.name.casefold())
                        if not unicodedata.combining(char)
                    ).strip() == normalized_province)
                    if len(matches) != 1:
                        matches = province_state.search([
                            ('country_id', '=', ar_country.id),
                            ('name', 'ilike', provincia),
                        ], limit=2)
                if len(matches) == 1:
                    vals['state_id'] = matches.id

        responsibility_code = data.get('responsibility_code')
        if responsibility_code and 'l10n_ar_afip_responsibility_type_id' in self._fields:
            responsibility = self.env['l10n_ar.afip.responsibility.type'].search([
                ('code', '=', responsibility_code),
            ], limit=2)
            if len(responsibility) == 1:
                vals['l10n_ar_afip_responsibility_type_id'] = responsibility.id

        activity_code = data.get('actividad_code')
        if activity_code and 'l10n_ar.arca.activity' in self.env and 'l10n_ar_arca_activity_id' in self._fields:
            activity = self.env['l10n_ar.arca.activity'].search([
                ('code', '=', activity_code),
            ], limit=1)
            if activity:
                vals['l10n_ar_arca_activity_id'] = activity.id
        return vals

    def action_l10n_ar_update_from_padron(self):
        """Consulta explícita y de solo lectura a ARCA; aplica datos solo tras validar respuesta."""
        warnings = []
        for partner in self:
            try:
                cuit = ''.join(char for char in (partner.vat or '') if char.isdigit())
                if not partner._l10n_ar_validate_cuit_checksum(cuit):
                    raise UserError(_(
                        "El CUIT '%s' no es válido. Debe contener 11 dígitos numéricos con dígito verificador Módulo 11 correcto."
                    ) % (partner.vat or ''))

                data = partner._l10n_ar_fetch_padron_data(cuit)
                partner.write(partner._l10n_ar_padron_partner_vals(data))
                warnings.extend(data.get('warnings') or [])
            except UserError as error:
                partner.write({'l10n_ar_padron_error': str(error)[:500]})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No se pudo consultar el Padrón ARCA'),
                        'message': str(error),
                        'type': 'danger',
                        'sticky': True,
                    },
                }
            except Exception:
                _logger.exception('Unexpected error while manually querying ARCA taxpayer registry')
                message = _('Ocurrió un error inesperado al consultar el Padrón. Revise el registro y los logs del servidor.')
                partner.write({'l10n_ar_padron_error': message})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No se pudo consultar el Padrón ARCA'),
                        'message': message,
                        'type': 'danger',
                        'sticky': True,
                    },
                }

        if warnings:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Padrón ARCA actualizado con observaciones'),
                    'message': _('Se cargaron los datos disponibles. ARCA informa: %s') % ' | '.join(warnings),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Padrón ARCA actualizado'),
                'message': _('Se actualizaron los datos disponibles desde el Padrón ARCA.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_l10n_ar_lookup_padron_draft(self, vat):
        """Lookup ARCA data for an unsaved contact without creating a partner."""
        digits = ''.join(char for char in (vat or '') if char.isdigit())
        draft = self.new({'vat': vat or False})
        if not draft._l10n_ar_validate_cuit_checksum(digits):
            return {
                'error': _(
                    "El CUIT '%s' no es válido. Debe contener 11 dígitos numéricos con dígito verificador Módulo 11 correcto."
                ) % (vat or ''),
            }

        try:
            data = draft._l10n_ar_fetch_padron_data(digits)
            values = draft._l10n_ar_padron_partner_vals(data)
            # FormController's relational model expects many2one values as
            # {id, display_name} objects when updating an unsaved form record.
            # The persisted-record action still consumes the integer IDs above.
            for field_name, value in list(values.items()):
                field = draft._fields.get(field_name)
                if field and field.type == 'many2one' and value:
                    related = self.env[field.comodel_name].browse(value)
                    values[field_name] = {
                        'id': related.id,
                        'display_name': related.display_name,
                    }
            return {
                'values': values,
                'warnings': data.get('warnings') or [],
            }
        except UserError as error:
            return {'error': str(error)[:500]}
        except Exception:
            _logger.exception('Unexpected error while querying ARCA registry for an unsaved partner')
            return {
                'error': _(
                    'Ocurrió un error inesperado al consultar el Padrón. Revise la conexión y los logs del servidor.'
                ),
            }

    def _l10n_ar_parse_padron_person(self, person_return):
        """Normaliza los campos oficiales de personaReturn sin inferencias por posición."""
        def local_name(element):
            return element.tag.rsplit('}', 1)[-1]

        def child(parent, name):
            if parent is None:
                return None
            return next((node for node in parent if local_name(node) == name), None)

        def text(parent, name):
            node = child(parent, name)
            return (node.text or '').strip() if node is not None else ''

        general = child(person_return, 'datosGenerales')
        # Observations ARCA attaches to the answer ("CUIT limitada", "pendiente
        # la constitución del domicilio fiscal electrónico"...). They do not
        # stop the lookup: the available data is loaded and the user is warned.
        warnings = []
        for section_name in ('errorConstancia', 'errorRegimenGeneral', 'errorMonotributo'):
            section = child(person_return, section_name)
            if section is None:
                continue
            for node in section.iter():
                if local_name(node) == 'error' and (node.text or '').strip():
                    message = (node.text or '').strip()
                    if message not in warnings:
                        warnings.append(message)
        if general is None:
            general = child(person_return, 'errorConstancia')
        if general is None:
            raise UserError(_('La respuesta del Padrón no incluye datos generales.'))
        name = text(general, 'razonSocial')
        if not name:
            name = ' '.join(part for part in (text(general, 'apellido'), text(general, 'nombre')) if part)
        if not name:
            raise UserError(_('ARCA no devolvió una razón social o nombre identificable.'))
        domicile = child(general, 'domicilioFiscal')

        tax_ids = set()
        activity_code = ''
        for section_name in ('datosRegimenGeneral', 'datosMonotributo'):
            section = child(person_return, section_name)
            if section is None:
                continue
            for node in section.iter():
                tag = local_name(node)
                if tag == 'impuesto' and text(node, 'estadoImpuesto').upper() == 'AC':
                    tax_id = text(node, 'idImpuesto')
                    if tax_id:
                        tax_ids.add(tax_id)
                elif tag == 'actividad' and not activity_code:
                    activity_code = text(node, 'idActividad')

        # Map only a single explicit IVA regime. Other simultaneous regimes
        # remain untouched because the Padrón response does not define one
        # unique responsibility type in that case.
        responsibility_code = ''
        iva_regimes = tax_ids.intersection({'20', '30', '32', '34'})
        if iva_regimes == {'30'}:
            responsibility_code = '1'  # IVA Responsable Inscripto
        elif iva_regimes == {'20'}:
            responsibility_code = '6'  # Responsable Monotributo
        elif iva_regimes == {'32'}:
            responsibility_code = '4'  # IVA Sujeto Exento
        elif iva_regimes == {'34'}:
            responsibility_code = '15'  # IVA No Alcanzado

        return {
            'name': name,
            'estadoClave': text(general, 'estadoClave'),
            'direccion': text(domicile, 'direccion') if domicile is not None else '',
            'localidad': text(domicile, 'localidad') if domicile is not None else '',
            'codPostal': text(domicile, 'codPostal') if domicile is not None else '',
            'provincia': text(domicile, 'descripcionProvincia') if domicile is not None else '',
            'responsibility_code': responsibility_code,
            'actividad_code': activity_code,
            'warnings': warnings,
        }
