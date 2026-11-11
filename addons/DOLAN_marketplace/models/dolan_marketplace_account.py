# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .providers import ADAPTERS

_logger = logging.getLogger(__name__)

PROVIDERS = [
    ('mercadolibre', 'Mercado Libre'),
    ('tiendanube', 'Tiendanube'),
]


class DolanMarketplaceAccount(models.Model):
    _name = 'dolan.marketplace.account'
    _description = 'Cuenta de marketplace'
    _inherit = ['mail.thread']
    _check_company_auto = True

    name = fields.Char(string='Nombre', required=True, tracking=True)
    provider = fields.Selection(PROVIDERS, string='Plataforma', required=True, default='mercadolibre', tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Sin conectar'),
        ('connected', 'Conectada'),
        ('error', 'Con error'),
    ], string='Estado', default='draft', required=True, tracking=True, copy=False)

    # Credenciales (sólo visibles para administradores de marketplaces)
    client_id = fields.Char(string='App ID / Client ID', groups='DOLAN_marketplace.group_marketplace_manager')
    client_secret = fields.Char(string='Clave secreta de la app', groups='DOLAN_marketplace.group_marketplace_manager')
    access_token = fields.Char(string='Access token', copy=False, groups='DOLAN_marketplace.group_marketplace_manager')
    refresh_token = fields.Char(string='Refresh token', copy=False, groups='DOLAN_marketplace.group_marketplace_manager')
    token_expiry = fields.Datetime(string='Vence el token', copy=False, readonly=True)
    remote_user_id = fields.Char(
        string='ID de vendedor / tienda', copy=False,
        help='Mercado Libre: ID del usuario vendedor (se completa al conectar). Tiendanube: ID de la tienda.',
    )
    remote_name = fields.Char(string='Cuenta remota', copy=False, readonly=True)
    api_contact = fields.Char(
        string='Contacto para la API', help='Tiendanube exige un correo de contacto en cada llamada (User-Agent).',
    )
    webhook_token = fields.Char(
        string='Token de webhook', copy=False, readonly=True, default=lambda self: secrets.token_urlsafe(24),
        groups='DOLAN_marketplace.group_marketplace_manager',
    )
    webhook_url = fields.Char(string='URL de notificaciones', compute='_compute_webhook_url')
    redirect_uri = fields.Char(string='URL de redirección OAuth', compute='_compute_webhook_url')

    # Operación
    warehouse_id = fields.Many2one('stock.warehouse', string='Depósito', check_company=True,
                                   help='Depósito del que se informa el stock y desde el que se entregan las ventas.')
    pricelist_id = fields.Many2one('product.pricelist', string='Lista de precios', check_company=True,
                                   help='Precio que se publica. Vacío: precio de venta del producto.')
    team_id = fields.Many2one('crm.team', string='Equipo de ventas', check_company=True)
    user_id = fields.Many2one('res.users', string='Vendedor asignado')
    fallback_product_id = fields.Many2one(
        'product.product', string='Producto para ventas sin vincular', check_company=True,
        help='Se usa cuando una venta trae una publicación que no está vinculada a un producto de Odoo.',
    )
    shipping_product_id = fields.Many2one('product.product', string='Producto de envío', check_company=True)
    prices_include_tax = fields.Boolean(string='Los precios publicados incluyen IVA', default=True)
    sync_stock = fields.Boolean(string='Sincronizar stock', default=True)
    sync_price = fields.Boolean(string='Sincronizar precio', default=True)
    stock_reserve = fields.Float(string='Reserva de stock', default=0.0,
                                 help='Unidades que no se publican para cubrir ventas por otros canales.')
    import_orders = fields.Boolean(string='Bajar ventas', default=True)
    auto_invoice = fields.Boolean(string='Facturar automáticamente', default=False,
                                  help='Crea y publica la factura al bajar una venta pagada.')
    last_order_sync = fields.Datetime(string='Última bajada de ventas', copy=False)

    listing_ids = fields.One2many('dolan.marketplace.listing', 'account_id', string='Publicaciones')
    listing_count = fields.Integer(compute='_compute_counts')
    order_count = fields.Integer(compute='_compute_counts')
    log_ids = fields.One2many('dolan.marketplace.log', 'account_id', string='Registro')

    def _compute_webhook_url(self):
        base_url = self.get_base_url()
        for account in self:
            token = account.sudo().webhook_token or ''
            path = 'ml' if account.provider == 'mercadolibre' else 'tn'
            account.webhook_url = '%s/dolan_marketplace/%s/notify/%s' % (base_url, path, token)
            account.redirect_uri = '%s/dolan_marketplace/ml/callback' % base_url

    def _compute_counts(self):
        for account in self:
            account.listing_count = len(account.listing_ids)
            account.order_count = self.env['sale.order'].search_count([('dolan_marketplace_account_id', '=', account.id)])

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _adapter(self):
        self.ensure_one()
        return ADAPTERS[self.provider](self.sudo())

    def _ensure_token(self):
        self.ensure_one()
        account = self.sudo()
        if account.provider != 'mercadolibre' or not account.refresh_token:
            return
        if account.token_expiry and account.token_expiry > fields.Datetime.now() + timedelta(minutes=5):
            return
        account._store_token(account._adapter().refresh_token())

    def _store_token(self, data):
        self.ensure_one()
        values = {'access_token': data.get('access_token')}
        if data.get('refresh_token'):
            values['refresh_token'] = data['refresh_token']
        if data.get('expires_in'):
            values['token_expiry'] = fields.Datetime.now() + timedelta(seconds=int(data['expires_in']))
        if data.get('user_id') and not self.remote_user_id:
            values['remote_user_id'] = str(data['user_id'])
        self.sudo().write(values)

    def _marketplace_request(self, method, url, auth=True, params=None, data=None, json=None):
        """Llamada HTTP a la plataforma. Devuelve el JSON o levanta UserError con el detalle."""
        self.ensure_one()
        headers = {'Accept': 'application/json'}
        if auth:
            self._ensure_token()
            headers.update(self._adapter().headers())
        try:
            response = requests.request(method, url, params=params, data=data, json=json, headers=headers, timeout=30)
        except requests.RequestException as error:
            raise UserError(_('No se pudo conectar con %(provider)s: %(error)s',
                              provider=self._provider_label(), error=error)) from error
        if response.status_code >= 400:
            raise UserError(_('%(provider)s respondió %(code)s: %(body)s', provider=self._provider_label(),
                              code=response.status_code, body=response.text[:500]))
        if not response.content:
            return {}
        return response.json()

    def _provider_label(self):
        return dict(PROVIDERS).get(self.provider, self.provider)

    def _log(self, operation, message, state='done', reference=False):
        self.ensure_one()
        return self.env['dolan.marketplace.log'].sudo().create({
            'account_id': self.id, 'operation': operation, 'state': state,
            'message': message, 'reference': reference,
        })

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------
    def _oauth_state(self):
        self.ensure_one()
        secret = self.env['ir.config_parameter'].sudo().get_str('database.secret') or ''
        signature = hmac.new(secret.encode(), str(self.id).encode(), hashlib.sha256).hexdigest()[:32]
        return '%s-%s' % (self.id, signature)

    @api.model
    def _account_from_oauth_state(self, state):
        account_id, _sep, signature = (state or '').partition('-')
        if not account_id.isdigit():
            return self.browse()
        account = self.sudo().browse(int(account_id)).exists()
        if account and hmac.compare_digest(account._oauth_state(), state):
            return account
        return self.browse()

    def action_connect(self):
        self.ensure_one()
        if self.provider != 'mercadolibre':
            return self.action_test_connection()
        if not (self.sudo().client_id and self.sudo().client_secret):
            raise UserError(_('Cargá el App ID y la clave secreta de tu aplicación de Mercado Libre.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self._adapter().authorization_url(self.redirect_uri, self._oauth_state()),
            'target': 'self',
        }

    def action_test_connection(self):
        for account in self:
            if account.provider == 'tiendanube' and not (account.sudo().access_token and account.remote_user_id):
                raise UserError(_('Cargá el ID de la tienda y el access token de Tiendanube.'))
            try:
                info = account._adapter().whoami()
            except UserError as error:
                account.state = 'error'
                account._log('connect', str(error), state='error')
                raise
            account.write({'state': 'connected', 'remote_name': info.get('name'),
                           'remote_user_id': account.remote_user_id or info.get('id')})
            account._log('connect', _('Conectada como %s') % (info.get('name') or info.get('id')))
        return True

    # ------------------------------------------------------------------
    # Publicaciones
    # ------------------------------------------------------------------
    def action_fetch_listings(self):
        Listing = self.env['dolan.marketplace.listing']
        for account in self:
            remote = account._adapter().fetch_listings()
            existing = {(l.item_id, l.variation_id or ''): l for l in account.with_context(active_test=False).listing_ids}
            created = linked = 0
            for entry in remote:
                key = (entry['item_id'], entry['variation_id'] or '')
                values = {
                    'title': entry['title'], 'remote_sku': entry['sku'], 'remote_price': entry['price'],
                    'remote_stock': entry['stock'], 'url': entry['url'],
                }
                listing = existing.get(key)
                if listing:
                    listing.write(values)
                else:
                    values.update({'account_id': account.id, 'item_id': entry['item_id'],
                                   'variation_id': entry['variation_id'] or False})
                    listing = Listing.create(values)
                    created += 1
                if not listing.product_id and listing._link_by_sku():
                    linked += 1
            account._log('listings', _('%(total)s publicaciones leídas, %(new)s nuevas, %(linked)s vinculadas por SKU.',
                                       total=len(remote), new=created, linked=linked))
        return True

    def action_sync_listings(self):
        for account in self:
            listings = account.listing_ids.filtered(lambda l: l.active and l.product_id and l.sync_enabled)
            listings._push()
        return True

    # ------------------------------------------------------------------
    # Ventas
    # ------------------------------------------------------------------
    def action_import_orders(self):
        for account in self:
            since = account.last_order_sync and account.last_order_sync - timedelta(hours=1)
            started = fields.Datetime.now()
            orders = account._adapter().fetch_orders(since)
            imported = 0
            for data in orders:
                if account._import_order_safe(data):
                    imported += 1
            account.last_order_sync = started
            account._log('orders', _('%(total)s ventas revisadas, %(new)s importadas.', total=len(orders), new=imported))
        return True

    def _import_order_by_id(self, remote_id):
        self.ensure_one()
        return self._import_order_safe(self._adapter().fetch_order(remote_id))

    def _import_order_safe(self, data):
        """Importa una venta dentro de un savepoint: un error no frena las demás."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                return self.env['sale.order']._dolan_marketplace_import(self, data)
        except UserError as error:
            _logger.warning('DOLAN marketplace: no se importó %s: %s', data.get('name'), error)
            self._log('orders', str(error), state='error', reference=data.get('name'))
            return False
        except Exception as error:  # noqa: BLE001 - se registra y sigue con la próxima venta
            _logger.exception('DOLAN marketplace: error importando %s', data.get('name'))
            self._log('orders', str(error), state='error', reference=data.get('name'))
            return False

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ventas de %s') % self.name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('dolan_marketplace_account_id', '=', self.id)],
        }

    def action_view_listings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Publicaciones de %s') % self.name,
            'res_model': 'dolan.marketplace.listing',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    # ------------------------------------------------------------------
    # Tareas programadas
    # ------------------------------------------------------------------
    @api.model
    def _cron_import_orders(self):
        for account in self.search([('state', '=', 'connected'), ('import_orders', '=', True)]):
            try:
                account.action_import_orders()
                self.env.cr.commit()
            except Exception as error:  # noqa: BLE001
                self.env.cr.rollback()
                account._log('orders', str(error), state='error')
                self.env.cr.commit()

    @api.model
    def _cron_sync_listings(self):
        for account in self.search([('state', '=', 'connected')]):
            try:
                account.action_sync_listings()
                self.env.cr.commit()
            except Exception as error:  # noqa: BLE001
                self.env.cr.rollback()
                account._log('listings', str(error), state='error')
                self.env.cr.commit()
