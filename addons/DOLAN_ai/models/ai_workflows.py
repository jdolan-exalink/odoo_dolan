# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.

import json
import re
import unicodedata
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class AiSessionWorkflows(models.Model):
    _inherit = 'ai.session'

    @api.model
    def _normalize_ai_request(self, text):
        value = unicodedata.normalize('NFKD', (text or '').lower())
        return ''.join(char for char in value if not unicodedata.combining(char))

    def _process_explicit_business_request(self, user_message):
        """Handle bounded Odoo workflows locally; never post, confirm, email, or send records."""
        text = user_message or ''
        normalized = self._normalize_ai_request(text)

        resumed = self._resume_pending_sales_draft_request(text, normalized)
        if resumed is not None:
            return resumed

        draft_result = self._process_sales_draft_request(text, normalized)
        if draft_result is not None:
            return draft_result

        calendar_result = self._process_calendar_request(text, normalized)
        if calendar_result is not None:
            return calendar_result

        business_read = self._process_contact_crm_read(text, normalized)
        if business_read is not None:
            return {'reply': business_read}
        return None

    def _create_workflow_response(self, reply, action=None, metadata=None):
        self.ensure_one()
        event = self.env['ai.session.event'].create({
            'ai_session_id': self.id,
            'role': 'assistant',
            'content': reply,
            'metadata': json.dumps(metadata, ensure_ascii=False) if metadata else False,
        })
        self.loop_state = 'completed'
        result = {
            'session_id': self.id,
            'event_id': event.id,
            'reply': reply,
            'provider': 'Odoo',
            'model': _('Consulta o borrador preparado en Odoo'),
        }
        if action:
            result['workflow_action'] = action
        return result

    def _process_sales_draft_request(self, text, normalized):
        asks_invoice = bool(re.search(r'\b(factura|factura de venta|comprobante de venta)\b', normalized))
        asks_quote = bool(re.search(r'\b(?:presu\w*|presp\w*|cotiza\w*|oferta comercial)\b', normalized))
        has_intent = bool(re.search(
            r'\b(crea(?:r|me)?|arma(?:r|me)?|prepara(?:r|me)?|genera(?:r|me)?|'
            r'hace(?:r|me|mos|gamos)?|necesito|quiero|borrador)\b', normalized,
        ))
        if not (has_intent and (asks_invoice or asks_quote)):
            return None

        requested_model = 'sale.order' if asks_quote and not asks_invoice else 'account.move'
        if requested_model not in self.env:
            return {'reply': _('No está instalada la aplicación necesaria para crear ese borrador. No se creó ningún registro.')}

        parsed = self._parse_sales_draft_details(text, quote=asks_quote and not asks_invoice)
        if not parsed.get('partner_query') or not parsed.get('product_query') or parsed.get('amount') is None:
            missing = []
            if not parsed.get('partner_query'):
                missing.append(_('cliente'))
            if not parsed.get('product_query'):
                missing.append(_('artículo o servicio'))
            if parsed.get('amount') is None:
                missing.append(_('importe'))
            return {'reply': _('Puedo preparar el borrador, pero no lo creé todavía. Indicame: %s.') % ', '.join(missing)}

        try:
            partner_matches = self.env['res.partner'].search([
                ('name', 'ilike', parsed['partner_query']),
                ('active', '=', True),
            ], limit=8)
            company_partners = partner_matches.filtered(lambda partner: not partner.company_id or partner.company_id == self.env.company)
            partner_matches = company_partners or partner_matches
            exact_partners = partner_matches.filtered(
                lambda partner: self._normalize_ai_request(partner.name) == self._normalize_ai_request(parsed['partner_query'])
            )
            partners = exact_partners or partner_matches
            if not partners:
                return {'reply': _('No encontré el cliente “%s”. No creé ningún borrador.') % parsed['partner_query']}
            if len(partners) > 1:
                names = ', '.join(partners[:5].mapped('display_name'))
                return {'reply': _('Encontré más de un cliente para “%(query)s”: %(names)s. Decime cuál corresponde; no creé ningún borrador.') % {
                    'query': parsed['partner_query'], 'names': names,
                }}
            partner = partners[0]

            products = self._find_ai_sale_products(parsed['product_query'], company=self.env.company)
            if not products:
                suggestions = self._suggest_ai_sale_products(parsed['product_query'], company=self.env.company)
                if suggestions:
                    lines = '\n'.join('%s. %s' % (index, product.display_name) for index, product in enumerate(suggestions, 1))
                    reply = _('No encontré exactamente “%(query)s” en el catálogo de %(company)s. ¿Cuál de estos artículos querés usar?\n%(options)s\nNo creé el presupuesto todavía.') % {
                        'query': parsed['product_query'], 'company': self.env.company.display_name, 'options': lines,
                    }
                    return {
                        'reply': reply,
                        'metadata': {'pending_sales_draft': parsed, 'partner_id': partner.id, 'company_id': self.env.company.id,
                                     'source_text': text,
                                     'product_options': suggestions.ids},
                    }
                return {'reply': _('No encontré el artículo o servicio “%s” en el catálogo. No creé ningún borrador. Revisá el nombre o agregá primero el artículo.') % parsed['product_query']}
            if len(products) > 1:
                names = ', '.join(products[:5].mapped('display_name'))
                return {'reply': _('Encontré varios artículos para “%(query)s”: %(names)s. Decime cuál corresponde; no creé ningún borrador.') % {
                    'query': parsed['product_query'], 'names': names,
                }}
            product = products[0]
            company = self.env.company
            taxes = product.with_company(company).taxes_id.filtered(
                lambda tax: not tax.company_id or tax.company_id == company
            )
            fiscal_position = partner.with_company(company).property_account_position_id
            if parsed.get('tax_percent') is not None:
                requested_tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'sale'), ('company_id', '=', company.id),
                    ('amount_type', '=', 'percent'), ('amount', '=', parsed['tax_percent']),
                    ('active', '=', True),
                ], limit=1)
                if not requested_tax:
                    return {'reply': _('No encuentro un impuesto de venta configurado de %(rate)s%% para %(company)s. No creé el presupuesto.') % {
                        'rate': self._format_ai_money(parsed['tax_percent']), 'company': company.display_name,
                    }}
                taxes = requested_tax
            if fiscal_position:
                taxes = fiscal_position.map_tax(taxes)
            amount = parsed['amount']

            if parsed['quote']:
                order_line_fields = self.env['sale.order.line']._fields
                line_values = {
                    'product_id': product.id,
                    'name': product.get_product_multiline_description_sale() if hasattr(product, 'get_product_multiline_description_sale') else product.display_name,
                    'product_uom_qty': parsed.get('quantity') or 1.0,
                    'price_unit': amount,
                }
                uom_field = 'product_uom_id' if 'product_uom_id' in order_line_fields else 'product_uom'
                if uom_field in order_line_fields and product.uom_id:
                    line_values[uom_field] = product.uom_id.id
                tax_field = 'tax_ids' if 'tax_ids' in order_line_fields else ('tax_id' if 'tax_id' in order_line_fields else False)
                if tax_field:
                    line_values[tax_field] = [(6, 0, taxes.ids)]
                order_values = {
                    'partner_id': partner.id,
                    'company_id': company.id,
                    'order_line': [(0, 0, line_values)],
                }
                if parsed.get('currency') == 'USD':
                    usd_pricelist = self.env['product.pricelist'].search([
                        ('currency_id.name', '=', 'USD'), ('company_id', 'in', [company.id, False]),
                    ], limit=1)
                    if not usd_pricelist:
                        reply = _('Para no mezclar empresas, no puedo usar la lista USD de otra compañía. %(company)s todavía no tiene una lista de precios propia en USD. ¿Querés que cree esa lista y continúe con el borrador? No se creó ningún presupuesto.') % {
                            'company': company.display_name,
                        }
                        return {
                            'reply': reply,
                            'metadata': {'pending_currency_setup': True, 'pending_sales_draft': parsed,
                                         'source_text': text, 'selected_product_id': product.id,
                                         'partner_id': partner.id, 'company_id': company.id},
                        }
                    order_values['pricelist_id'] = usd_pricelist.id
                order = self.env['sale.order'].with_company(company).create(order_values)
                label = _('presupuesto')
                record = order
                route = 'sale.order'
            else:
                move_line_fields = self.env['account.move.line']._fields
                line_values = {
                    'product_id': product.id,
                    'name': product.display_name,
                    'quantity': parsed.get('quantity') or 1.0,
                    'price_unit': amount,
                }
                if 'product_uom_id' in move_line_fields and product.uom_id:
                    line_values['product_uom_id'] = product.uom_id.id
                if 'tax_ids' in move_line_fields:
                    line_values['tax_ids'] = [(6, 0, taxes.ids)]
                invoice_values = {
                    'move_type': 'out_invoice',
                    'partner_id': partner.id,
                    'company_id': company.id,
                    'invoice_date': fields.Date.context_today(self),
                    'invoice_line_ids': [(0, 0, line_values)],
                }
                if 'fiscal_position_id' in self.env['account.move']._fields and fiscal_position:
                    invoice_values['fiscal_position_id'] = fiscal_position.id
                record = self.env['account.move'].with_company(company).create(invoice_values)
                label = _('factura borrador')
                route = 'account.move'

            record_currency = record.currency_id if 'currency_id' in record._fields else company.currency_id
            amount_display = '%s %s' % (record_currency.name, self._format_ai_money(record.amount_total))
            reply = _(
                'Preparé el %(kind)s **%(number)s** para **%(partner)s** con **%(product)s**. '
                'Total calculado por Odoo: %(total)s. Está en borrador para que revises cliente, impuestos, '
                'importe y datos fiscales. No lo confirmé, contabilicé ni envié.'
            ) % {
                'kind': label, 'number': record.display_name, 'partner': partner.display_name,
                'product': product.display_name, 'total': amount_display,
            }
            return {
                'reply': reply,
                'action': {
                    'type': 'ir.actions.act_window',
                    'name': label,
                    'res_model': route,
                    'res_id': record.id,
                    'views': [[False, 'form']],
                    'view_mode': 'form',
                    'target': 'current',
                },
            }
        except (AccessError, UserError) as exc:
            return {'reply': _('No pude crear el borrador: %s. No se confirmó ni envió ningún comprobante.') % str(exc)}

    @api.model
    def _parse_sales_draft_details(self, text, quote=False):
        amount_match = re.search(
            r'\b(?:a|por|importe|total|valor)\s+(?:(?:usd|u\$s|ars|dolares?)\s*)?\$?\s*([0-9][0-9.,]*)'
            r'|\b(?:usd|u\$s|dolares?)\s*\$?\s*([0-9][0-9.,]*)|\$\s*([0-9][0-9.,]*)',
            self._normalize_ai_request(text), re.IGNORECASE,
        )
        amount_raw = next((value for value in amount_match.groups() if value), None) if amount_match else None
        amount = self._parse_localized_amount(amount_raw) if amount_raw else None
        quantity_match = re.search(r'\b(\d{1,4})\s+(?=(?:unidades?|u\.?|camaras?|camara|equipos?|articulos?|productos?)\b)', self._normalize_ai_request(text))
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        normalized = self._normalize_ai_request(text)
        currency = 'USD' if re.search(r'\b(?:usd|u\$s|dolares?)\b', normalized) else False
        tax_match = re.search(r'\biva\s*(\d{1,2}(?:[.,]\d+)?)\s*%', normalized)
        tax_percent = self._parse_localized_amount(tax_match.group(1)) if tax_match else None
        partner_match = re.search(
            r'\b(?:para|a)\s+(.+?)(?=\s+\b(?:de|por|importe|total|valor|en|con|pasame|dame|a)\b|$)', text, re.IGNORECASE,
        )
        partner_query = re.sub(r'^(?:el\s+)?(?:cliente|contacto)\s+', '', partner_match.group(1).strip(), flags=re.IGNORECASE) if partner_match else ''
        product_query = ''
        product_match = re.search(
            r'\b\d{1,4}\s+(?:(?:unidades?|u\.?|camaras?|camara|equipos?|articulos?|productos?)\s+)?'
            r'(.+?)\s+(?=(?:a|por|importe|total|valor)\s+(?:(?:usd|u\$s|ars|dolares?)\s*)?\$?\s*\d)',
            normalized, re.IGNORECASE,
        )
        if not product_match:
            product_match = re.search(
                r'\b(?:de|articulo|producto|servicio)\s+(.+?)\s+(?=(?:a|por|importe|total|valor)\s+(?:(?:usd|u\$s|ars|dolares?)\s*)?\$?\s*\d)',
                normalized, re.IGNORECASE,
            )
        if product_match:
            product_query = re.sub(r'\s+(?:pasame|dame|cotiza|ofrece)\b.*$', '', product_match.group(1)).strip(' .,;')
        return {
            'quote': quote, 'partner_query': partner_query, 'product_query': product_query,
            'amount': amount, 'quantity': quantity, 'currency': currency, 'tax_percent': tax_percent,
        }

    def _find_ai_sale_products(self, query, company):
        Product = self.env['product.product']
        domain = [('active', '=', True), ('sale_ok', '=', True), ('company_id', 'in', [company.id, False])]
        exact = Product.search(domain + [('name', '=ilike', query)], limit=8)
        if exact:
            return exact
        exact = Product.search(domain + [('default_code', '=ilike', query)], limit=8)
        if exact:
            return exact
        return Product.search(domain + [('name', 'ilike', query)], limit=8)

    def _suggest_ai_sale_products(self, query, company):
        tokens = re.findall(r'[a-z]+|\d+', self._normalize_ai_request(query))
        searchable = [token for token in tokens if len(token) >= 3]
        if not searchable:
            return self.env['product.product']
        Product = self.env['product.product']
        domain = [('active', '=', True), ('sale_ok', '=', True), ('company_id', 'in', [company.id, False])]
        numeric_tokens = [token for token in searchable if token.isdigit() and len(token) >= 3]
        token = numeric_tokens[0] if numeric_tokens else searchable[-1]
        candidates = Product.search(domain + [('name', 'ilike', token)], order='name asc', limit=30)
        camera_candidates = candidates.filtered(lambda product: re.search(r'camara|camera', self._normalize_ai_request(product.name)))
        return (camera_candidates or candidates)[:5]

    def _resume_pending_sales_draft_request(self, text, normalized):
        self.ensure_one()
        last_assistant = self.env['ai.session.event'].search([
            ('ai_session_id', '=', self.id), ('role', '=', 'assistant'),
        ], order='id desc', limit=1)
        if not last_assistant or not last_assistant.metadata:
            return None
        try:
            metadata = json.loads(last_assistant.metadata)
        except (TypeError, ValueError):
            return None
        pending = metadata.get('pending_sales_draft')
        product_ids = metadata.get('product_options') or []
        if not pending:
            return None
        if metadata.get('pending_currency_setup'):
            accepts_setup = bool(re.search(r'\b(?:si|dale|ok|crea|creala|configura|configurala|continua)\b', normalized))
            if not accepts_setup:
                return None
            company = self.env['res.company'].browse(metadata.get('company_id')).exists()
            if not company or company not in self.env.companies:
                return {'reply': _('No puedo configurar precios USD para esa empresa con tu usuario.')}
            pricelist = self.env['product.pricelist'].search([
                ('company_id', '=', company.id), ('currency_id.name', '=', 'USD'),
            ], limit=1)
            if not pricelist:
                usd = self.env['res.currency'].search([('name', '=', 'USD'), ('active', '=', True)], limit=1)
                if not usd:
                    return {'reply': _('La moneda USD no está activa en Odoo. No creé la lista ni el presupuesto.')}
                pricelist = self.env['product.pricelist'].create({
                    'name': _('Default USD - %s') % company.display_name,
                    'currency_id': usd.id,
                    'company_id': company.id,
                })
            source_text = metadata.get('source_text') or ''
            return self._process_sales_draft_request(source_text, self._normalize_ai_request(source_text))
        if not product_ids:
            return None
        # Solo una elección explícita ("2", "la 2", "opción 2"), no cualquier
        # número suelto dentro de otro pedido.
        choice = re.fullmatch(
            r'\s*(?:(?:la|el|usa|usá|quiero|elijo)\s+)?(?:(?:opcion|opcion numero|numero|nro\.?)\s*)?(\d)\s*[.!]?\s*',
            normalized,
        )
        if choice:
            index = int(choice.group(1)) - 1
            if 0 <= index < len(product_ids):
                product = self.env['product.product'].browse(product_ids[index]).exists()
                if product:
                    source_text = metadata.get('source_text') or ''
                    replacement = re.sub(re.escape(pending.get('product_query') or ''), product.name, source_text, flags=re.IGNORECASE)
                    return self._process_sales_draft_request(replacement, self._normalize_ai_request(replacement))
        if len(normalized.split()) <= 4 and re.search(r'\b(?:primera|primero|segunda|segundo|tercera|tercero)\b', normalized):
            words = {'primera': 0, 'primero': 0, 'segunda': 1, 'segundo': 1, 'tercera': 2, 'tercero': 2}
            index = next((value for key, value in words.items() if key in normalized), -1)
            if 0 <= index < len(product_ids):
                product = self.env['product.product'].browse(product_ids[index]).exists()
                if product:
                    source_text = metadata.get('source_text') or ''
                    replacement = re.sub(re.escape(pending.get('product_query') or ''), product.name, source_text, flags=re.IGNORECASE)
                    return self._process_sales_draft_request(replacement, self._normalize_ai_request(replacement))
        return None

    @api.model
    def _parse_localized_amount(self, raw):
        value = re.sub(r'[^0-9,.]', '', raw or '')
        if ',' in value and '.' in value:
            value = value.replace('.', '').replace(',', '.')
        elif ',' in value:
            value = value.replace(',', '.')
        elif '.' in value and len(value.rsplit('.', 1)[-1]) == 3:
            value = value.replace('.', '')
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _process_calendar_request(self, text, normalized):
        explicit_create = bool(re.search(
            r'\b(agendar|agendame|programa|programar|anota|anotame|crear|crea|creame)\b', normalized,
        ))
        agenda_imperative = bool(re.search(r'\bagenda\s+(?:un[oa]?\s+)?(?:evento|reunion|turno|cita)\b', normalized))
        wants_create = (explicit_create or agenda_imperative) and bool(
            re.search(r'\b(calendario|agenda|evento|reunion|turno|cita)\b', normalized)
        )
        asks_read = bool(re.search(r'\b(calendario|agenda|eventos?|reuniones?|turnos?|citas?)\b', normalized)) and bool(
            re.search(r'\b(que|leer|ver|mostrar|mostrame|consulta|consultar|tengo|proximos?|proximas?|hoy|manana|semana)\b', normalized)
        )
        if wants_create:
            if 'calendar.event' not in self.env:
                return {'reply': _('La aplicación Calendario no está instalada o no tenés acceso; no creé ningún evento.')}
            return self._create_calendar_event_from_request(text, normalized)
        if asks_read:
            if 'calendar.event' not in self.env:
                return {'reply': _('La aplicación Calendario no está instalada o no tenés acceso.')}
            return {'reply': self._read_calendar_for_request(normalized)}
        return None

    def _create_calendar_event_from_request(self, text, normalized):
        date_value = self._requested_date(normalized)
        time_match = re.search(
            r'\ba\s+las?\s+([01]?\d|2[0-3])(?:[:.]([0-5]\d))?\b'
            r'|\b([01]?\d|2[0-3])[:.]([0-5]\d)\b'
            r'|\b([01]?\d|2[0-3])\s*(?:hs?|horas?)\b',
            normalized,
        )
        if not date_value or not time_match:
            missing = _('fecha y hora') if not date_value and not time_match else (_('fecha') if not date_value else _('hora'))
            return {'reply': _('No agendé nada todavía. Para crear el evento indicame %s.') % missing}
        hour = int(next(value for value in time_match.groups()[::2] if value is not None))
        minute = int(next((value for value in time_match.groups()[1::2] if value is not None), 0))
        title = re.sub(
            r'\b(agenda|agendar|agendame|programa|programar|anota|anotame|crear|crea|en|el|la|hoy|manana|'
            r'\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2}|a\s+las?|[01]?\d|2[0-3])\b',
            ' ', text, flags=re.IGNORECASE,
        )
        title = re.sub(r'\b(?:calendario|evento|reunion|turno|cita|hs?|horas?)\b', ' ', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title).strip(' ,.;:-') or _('Reunión')
        try:
            tz = pytz.timezone(self.env.user.tz or 'UTC')
            local_start = tz.localize(datetime.combine(date_value, time(hour, minute)))
            start_utc = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            stop_utc = start_utc + timedelta(hours=1)
            event = self.env['calendar.event'].create({
                'name': title[:128],
                'start': fields.Datetime.to_string(start_utc),
                'stop': fields.Datetime.to_string(stop_utc),
                'user_id': self.env.uid,
                'allday': False,
            })
        except (AccessError, UserError) as exc:
            return {'reply': _('No pude crear el evento: %s.') % str(exc)}
        return {
            'reply': _('Agendé “%(title)s” para el %(date)s a las %(time)s. El evento quedó en tu calendario; no invité asistentes ni envié notificaciones.') % {
                'title': event.name,
                'date': date_value.strftime('%d/%m/%Y'),
                'time': '%02d:%02d' % (hour, minute),
            },
            'action': {
                'type': 'ir.actions.act_window', 'res_model': 'calendar.event', 'res_id': event.id,
                'views': [[False, 'form']], 'view_mode': 'form', 'target': 'current',
            },
        }

    @api.model
    def _requested_date(self, normalized):
        today = fields.Date.context_today(self)
        if re.search(r'\bmanana\b', normalized):
            return today + timedelta(days=1)
        if re.search(r'\bhoy\b', normalized):
            return today
        match = re.search(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', normalized)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3) or today.year)
            if year < 100:
                year += 2000
            try:
                return datetime(year, month, day).date()
            except ValueError:
                return None
        iso = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', normalized)
        if iso:
            try:
                return datetime.strptime(iso.group(0), '%Y-%m-%d').date()
            except ValueError:
                return None
        return None

    def _read_calendar_for_request(self, normalized):
        start_date = self._requested_date(normalized) or fields.Date.context_today(self)
        if 'manana' in normalized:
            end_date = start_date + timedelta(days=1)
        elif 'semana' in normalized or 'proximos' in normalized or 'proximas' in normalized:
            end_date = start_date + timedelta(days=7)
        else:
            end_date = start_date + timedelta(days=1)
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        start_local = tz.localize(datetime.combine(start_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end_local = tz.localize(datetime.combine(end_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        partner_id = self.env.user.partner_id.id
        events = self.env['calendar.event'].search([
            ('start', '>=', fields.Datetime.to_string(start_local)),
            ('start', '<', fields.Datetime.to_string(end_local)),
            '|', ('user_id', '=', self.env.uid), ('partner_ids', 'in', [partner_id]),
        ], order='start asc', limit=30)
        title = _('Agenda del %(start)s al %(end)s') % {
            'start': start_date.strftime('%d/%m/%Y'), 'end': (end_date - timedelta(days=1)).strftime('%d/%m/%Y'),
        }
        if not events:
            return '%s\n%s' % (title, _('No encontré eventos para ese período.'))
        rows = [title]
        for event in events:
            local_start = fields.Datetime.to_datetime(event.start).replace(tzinfo=pytz.UTC).astimezone(tz)
            rows.append('- %s · %s · %s' % (local_start.strftime('%d/%m %H:%M'), event.name, event.location or _('sin ubicación')))
        return '\n'.join(rows)

    # Temas que no son una ficha de contacto aunque mencionen "cliente" o
    # "proveedor": se dejan para los reportes y el modelo con herramientas.
    _AI_NON_CONTACT_TOPICS = (
        r'\b(facturaci[oó]n|facturas?|facturad[oa]s?|factur[eé]|ventas?|vend\w*|compras?|cobranzas?|cobr\w*|'
        r'deudas?|deben?|adeud\w*|saldos?|pagos?|pagar|pendientes?|vencid[oa]s?|iva|impuestos?|'
        r'pedidos?|presupuestos?|ranking|top|totales?|importes?|montos?|stock|productos?)\b'
    )

    def _process_contact_crm_read(self, text, normalized):
        asks_crm = bool(re.search(r'\b(crm|oportunidades?|pipeline|leads?|prospectos?)\b', normalized))
        asks_contact = bool(re.search(r'\b(contactos?|clientes?|proveedores?|cuit|cuil|telefono|correo|email)\b', normalized))
        asks_read = bool(re.search(r'\b(busca|buscar|consulta|consultar|mostra|mostrame|mostrar|lista|listar|datos|estado|resumen|quien|quienes|informacion)\b', normalized))
        if asks_crm and (asks_read or re.search(r'\b(oportunidades?|pipeline|leads?)\b', normalized)):
            return {'reply': self._read_crm_for_request(normalized)}
        if asks_contact and asks_read and not re.search(self._AI_NON_CONTACT_TOPICS, normalized):
            return {'reply': self._read_contacts_for_request(text, normalized)}
        return None

    def _read_contacts_for_request(self, text, normalized):
        query = ''
        match = re.search(r'\b(?:contacto|cliente|proveedor)\s+(?:de\s+|llamado\s+|llamada\s+)?(.+?)(?=\s+(?:con|y|telefono|correo|cuit|cuil)\b|$)', text, re.IGNORECASE)
        if match:
            query = match.group(1).strip(' .,:;')
        if not query:
            match = re.search(r'\b(?:de|para)\s+(.+?)(?=\s+(?:con|y|telefono|correo|cuit|cuil)\b|$)', text, re.IGNORECASE)
            if match:
                query = match.group(1).strip(' .,:;')
        Partner = self.env['res.partner']
        domain = [('active', '=', True)]
        if query:
            domain.append(('name', 'ilike', query))
        records = Partner.search(domain, order='name asc', limit=10)
        if not records:
            return _('No encontré contactos que coincidan con “%s”.') % query if query else _('No encontré contactos.')
        rows = [_('Contactos encontrados:')]
        for partner in records:
            details = [partner.display_name]
            if partner.vat:
                details.append(_('CUIT/CUIL: %s') % partner.vat)
            if partner.email:
                details.append(_('email: %s') % partner.email)
            if partner.phone or partner.mobile:
                details.append(_('teléfono: %s') % (partner.phone or partner.mobile))
            address = ', '.join(part for part in (partner.street, partner.city, partner.state_id.name) if part)
            if address:
                details.append(_('domicilio: %s') % address)
            rows.append('- ' + ' · '.join(details))
        return '\n'.join(rows)

    def _read_crm_for_request(self, normalized):
        if 'crm.lead' not in self.env:
            return _('La aplicación CRM no está instalada o no tenés acceso.')
        Lead = self.env['crm.lead']
        domain = [('active', '=', True)]
        companies = self.env.companies
        if 'company_id' in Lead._fields and companies:
            domain.append(('company_id', 'in', companies.ids + [False]))
        query = re.search(r'\b(?:oportunidad|lead|prospecto)\s+(?:de|llamada|llamado)?\s*([a-z0-9][\w\s.-]{2,50})', normalized)
        if query:
            domain.append(('name', 'ilike', query.group(1).strip()))
        leads = Lead.search(domain, order='write_date desc, id desc', limit=20)
        if not leads:
            return _('No encontré oportunidades o leads activos que coincidan con la consulta.')
        lines = [_('Oportunidades y leads de CRM:')]
        for lead in leads:
            amount = ''
            if 'expected_revenue' in lead._fields and lead.expected_revenue:
                currency = lead.company_currency if 'company_currency' in lead._fields else lead.company_id.currency_id
                amount = _(' · esperado: %s %s') % (currency.name if currency else '', self._format_ai_money(lead.expected_revenue))
            partner = _(' · cliente: %s') % lead.partner_id.display_name if lead.partner_id else ''
            stage = _(' · etapa: %s') % lead.stage_id.display_name if lead.stage_id else ''
            company = _(' · empresa: %s') % lead.company_id.display_name if lead.company_id else ''
            deadline = _(' · próxima actividad: %s') % fields.Date.to_string(lead.date_deadline) if lead.date_deadline else ''
            lines.append('- %s%s%s%s%s%s' % (lead.display_name, partner, stage, amount, deadline, company))
        return '\n'.join(lines)

    @api.model
    def _format_ai_money(self, value):
        return f'{value:,.2f}'.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
