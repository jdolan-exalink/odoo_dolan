# -*- coding: utf-8 -*-
import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import Request, urlopen

from odoo import api, fields, models, _
from odoo.exceptions import UserError


BNA_URL = 'https://www.bna.com.ar/Personas'


class _BnaTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._table = []
        self._row = []
        self._cell = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._in_table = True
            self._table = []
        elif tag == 'tr' and self._in_table:
            self._in_row = True
            self._row = []
        elif tag in ('td', 'th') and self._in_row:
            self._in_cell = True
            self._cell = []

    def handle_data(self, data):
        self.text_parts.append(data)
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._in_cell:
            self._row.append(' '.join(self._cell).strip())
            self._in_cell = False
        elif tag == 'tr' and self._in_row:
            if self._row:
                self._table.append(self._row)
            self._in_row = False
        elif tag == 'table' and self._in_table:
            if self._table:
                self.tables.append(self._table)
            self._in_table = False


class DolanBnaExchangeRate(models.Model):
    _name = 'dolan.bna.exchange.rate'
    _description = 'Cotización de dólar vendedor del Banco Nación'
    _order = 'rate_date desc, fetched_at desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Referencia', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, index=True, default=lambda self: self.env.company)
    rate_date = fields.Date(string='Fecha de cotización BNA', required=True, index=True)
    rate = fields.Float(string='Venta BNA (ARS por USD)', digits=(16, 4), required=True)
    market = fields.Selection([('billetes', 'Billetes')], string='Mercado', default='billetes', required=True)
    operation = fields.Selection([('sell', 'Venta')], string='Operación', default='sell', required=True)
    fetched_at = fields.Datetime(string='Consultado el', required=True, default=fields.Datetime.now)
    source_url = fields.Char(string='Fuente', required=True, default=BNA_URL)

    _positive_rate = models.Constraint(
        'CHECK(rate > 0)', 'El tipo de cambio debe ser mayor que cero.',
    )

    @api.depends('rate_date', 'rate', 'company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = _('BNA Venta USD · %(date)s · %(rate)s') % {
                'date': fields.Date.to_string(rec.rate_date) if rec.rate_date else '',
                'rate': ('%.4f' % rec.rate) if rec.rate else '',
            }

    @api.model
    def fetch_bna_selling_rate(self, company=None):
        company = company or self.env.company
        request = Request(BNA_URL, headers={
            'User-Agent': 'DOLAN-ERP/1.0 (cotizacion cambiaria)',
            'Accept': 'text/html,application/xhtml+xml',
        })
        try:
            with urlopen(request, timeout=12) as response:
                html = response.read(2_000_000).decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        except (URLError, TimeoutError, OSError) as exc:
            raise UserError(_('No pude consultar la página oficial del BNA. No se aplicó ninguna conversión. Detalle: %s') % str(exc))

        parser = _BnaTableParser()
        parser.feed(html)
        selected = None
        for table in parser.tables:
            for row in table:
                if len(row) >= 3 and 'dolar' in _normalize(row[0]) and 'usa' in _normalize(row[0]):
                    selected = row
                    break
            if selected:
                break
        if not selected:
            raise UserError(_('La página del BNA cambió o no publicó la tabla de Cotización Billetes. No se aplicó ninguna conversión.'))

        rate = _parse_argentine_amount(selected[-1])
        if not rate or rate <= 0:
            raise UserError(_('No pude interpretar la cotización de venta del dólar billete del BNA. No se aplicó ninguna conversión.'))

        page_text = ' '.join(parser.text_parts)
        date_match = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', page_text)
        if date_match:
            try:
                rate_date = datetime(int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1))).date()
            except ValueError:
                raise UserError(_('El BNA publicó una fecha de cotización inválida. No se aplicó ninguna conversión.'))
        else:
            rate_date = fields.Date.context_today(self)

        values = {
            'company_id': company.id,
            'rate_date': rate_date,
            'rate': rate,
            'market': 'billetes',
            'operation': 'sell',
            'fetched_at': fields.Datetime.now(),
            'source_url': BNA_URL,
        }
        existing = self.sudo().search([
            ('company_id', '=', company.id),
            ('rate_date', '=', rate_date),
            ('market', '=', 'billetes'),
            ('operation', '=', 'sell'),
        ], limit=1)
        if existing:
            existing.write(values)
            return existing
        return self.sudo().create(values)

    @api.model
    def _latest_for_company(self, company):
        return self.sudo().search([
            ('company_id', '=', company.id),
            ('market', '=', 'billetes'),
            ('operation', '=', 'sell'),
        ], order='rate_date desc, fetched_at desc, id desc', limit=1)


def _normalize(value):
    value = unicodedata.normalize('NFKD', (value or '').lower())
    return ''.join(char for char in value if char.isalnum() and not unicodedata.combining(char))


def _parse_argentine_amount(value):
    raw = re.sub(r'[^0-9,.]', '', (value or '').replace('\xa0', ''))
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif raw.count('.') > 1 or ('.' in raw and len(raw.rsplit('.', 1)[-1]) == 3):
        raw = raw.replace('.', '')
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
