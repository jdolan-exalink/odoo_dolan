import ipaddress
import base64
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tools import config


class DolanPaymentTerminal(models.Model):
    _name = 'dolan.payment.terminal'
    _description = 'Terminal de cobro'
    _check_company_auto = True

    name = fields.Char(string='Nombre', required=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, index=True)
    provider = fields.Selection([('clover', 'Clover'), ('mp_point', 'Mercado Pago Point'),
                                 ('mp_qr', 'Mercado Pago QR')], required=True, string='Proveedor')
    provider_brand = fields.Char(string='Marca', compute='_compute_provider_brand')
    journal_id = fields.Many2one('account.journal', string='Diario de cobro', check_company=True,
                                domain="[('type', 'in', ['bank', 'cash'])]")
    clover_ip = fields.Char(string='IP de Clover', help='Dirección IPv4 privada de la terminal en la red local.')
    clover_port = fields.Integer(string='Puerto', default=12345)
    clover_remote_app_id = fields.Char(string='Identificador de aplicación Clover', default='clover-bridge',
                                       help='Identificador utilizado por la integración autorizada en la terminal.')
    clover_pair_status = fields.Char(string='Estado de emparejamiento', compute='_compute_pair_status')
    clover_status_prefix = fields.Char(compute='_compute_status_prefix')
    clover_paired = fields.Boolean(string='Vinculado con Clover', default=False, readonly=True, copy=False)
    clover_auth_token_encrypted = fields.Char(string='Token Clover cifrado', readonly=True, copy=False,
                                              groups='base.group_system')
    mp_device_id = fields.Char(string='Identificador de terminal Point')
    mp_external_pos_id = fields.Char(string='Identificador de caja QR')
    active = fields.Boolean(default=True)

    @api.depends('provider', 'clover_paired')
    def _compute_pair_status(self):
        for terminal in self:
            terminal.clover_pair_status = _('Emparejado') if terminal.provider == 'clover' and terminal.clover_paired else (
                _('Sin emparejar') if terminal.provider == 'clover' else _('No aplica'))

    @api.depends('provider')
    def _compute_provider_brand(self):
        labels = {'clover': _('Clover'), 'mp_point': _('Mercado Pago Point'), 'mp_qr': _('Mercado Pago QR')}
        for terminal in self:
            terminal.provider_brand = labels.get(terminal.provider, '')

    def _compute_status_prefix(self):
        for terminal in self:
            terminal.clover_status_prefix = (
                f'dolan-clover-live-{self.env.cr.dbname}-{terminal.id}-{terminal.clover_ip}-'
                if terminal.provider == 'clover' else ''
            )

    @api.model
    def _clover_token_cipher(self):
        master_password = config.get('admin_passwd')
        if not master_password:
            raise UserError(_('No se puede conservar el emparejamiento: configurá admin_passwd en el servidor Odoo.'))
        key_material = f'dolan-clover-token-v1:{self.env.cr.dbname}:{master_password}'.encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
        return Fernet(key)

    def _clover_token_decrypt(self):
        self.ensure_one()
        if not self.clover_auth_token_encrypted:
            return False
        try:
            return self._clover_token_cipher().decrypt(self.clover_auth_token_encrypted.encode()).decode()
        except (InvalidToken, UnicodeDecodeError):
            self.write({'clover_auth_token_encrypted': False, 'clover_paired': False})
            return False

    def action_store_clover_pairing(self, authentication_token):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system') or self.company_id not in self.env.companies:
            raise AccessError(_('Solo un administrador de la empresa seleccionada puede guardar el vínculo Clover.'))
        if self.provider != 'clover' or not self.active:
            raise UserError(_('La terminal Clover debe estar activa.'))
        if not isinstance(authentication_token, str) or not authentication_token.strip() or len(authentication_token) > 4096:
            raise ValidationError(_('Clover no devolvió un token de emparejamiento válido.'))
        encrypted = self._clover_token_cipher().encrypt(authentication_token.strip().encode()).decode()
        self.write({'clover_auth_token_encrypted': encrypted, 'clover_paired': True})
        return True

    @api.constrains('clover_ip', 'clover_port', 'provider')
    def _check_clover_address(self):
        for terminal in self:
            if terminal.provider != 'clover' or not terminal.clover_ip:
                continue
            try:
                ip = ipaddress.IPv4Address(terminal.clover_ip)
            except ValueError:
                raise ValidationError(_('Ingresá una dirección IPv4 válida para Clover.'))
            if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                raise ValidationError(_('Ingresá una IP privada de la red local de la terminal.'))
            if not 1 <= terminal.clover_port <= 65535:
                raise ValidationError(_('El puerto debe estar entre 1 y 65535.'))

    def action_probe_clover(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede configurar o emparejar terminales.'))
        if self.provider != 'clover' or not self.clover_ip:
            raise UserError(_('Configurá primero la IP de la terminal Clover.'))
        return self._clover_connection_action('integrate')

    def action_test_clover(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Solo un administrador puede probar una terminal Clover.'))
        if self.provider != 'clover' or not self.clover_ip:
            raise UserError(_('Configurá primero la IP de la terminal Clover.'))
        return self._clover_connection_action('test')

    def _clover_connection_action(self, flow):
        self.ensure_one()
        auth_token = self._clover_token_decrypt()
        return {'type': 'ir.actions.client', 'tag': 'dolan_terminal_probe',
                'name': _('Integrar Clover') if flow == 'integrate' else _('Prueba de cobro Clover'),
                'params': {'host': self.clover_ip, 'port': self.clover_port, 'name': self.name,
                           'terminal_id': self.id, 'remote_app_id': self.clover_remote_app_id or 'clover-bridge',
                           'lease_prefix': f'dolan-clover-live-{self.env.cr.dbname}-{self.id}-{self.clover_ip}-',
                           'auth_token': auth_token, 'clover_paired': self.clover_paired,
                           'auto_connect': True, 'flow': flow}}

    def action_begin_clover_test(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system') or self.company_id not in self.env.companies:
            raise AccessError(_('Solo un administrador de la empresa seleccionada puede iniciar esta prueba.'))
        if self.provider != 'clover' or not self.active:
            raise UserError(_('La terminal Clover debe estar activa.'))
        currency = self.env.ref('base.ARS', raise_if_not_found=False)
        if not currency:
            raise UserError(_('No está configurada la moneda ARS.'))
        external_id = 'T' + uuid.uuid4().hex[:11]
        try:
            with self.env.cr.savepoint():
                operation = self.env['dolan.payment.operation'].sudo().create({
                    'company_id': self.company_id.id, 'terminal_id': self.id,
                    'currency_id': currency.id, 'amount': 10, 'operation_kind': 'test', 'state': 'dispatching',
                    'external_id': external_id, 'initiated_by': self.env.user.id,
                    'detail': 'Prueba Clover de $10. Resultado pendiente de confirmación.',
                })
        except IntegrityError:
            raise UserError(_('La terminal tiene una operación pendiente o en revisión. Revisala antes de intentar otro cobro.'))
        return {'operation_id': operation.id, 'external_id': external_id}

    def action_report_clover_test(self, operation_id, outcome, provider_reference=False):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system') or self.company_id not in self.env.companies:
            raise AccessError(_('No tenés permiso para informar este resultado.'))
        if outcome not in ('success', 'cancelled', 'uncertain'):
            raise UserError(_('Resultado desconocido.'))
        operation = self.env['dolan.payment.operation'].sudo().search([
            ('id', '=', operation_id), ('terminal_id', '=', self.id),
            ('company_id', '=', self.company_id.id), ('initiated_by', '=', self.env.user.id),
            ('operation_kind', '=', 'test'), ('amount', '=', 10), ('currency_id.name', '=', 'ARS'),
        ], limit=1)
        if not operation:
            raise UserError(_('No se encontró la operación de prueba.'))
        self.env.cr.execute('SELECT id FROM dolan_payment_operation WHERE id = %s FOR UPDATE', [operation.id])
        operation.invalidate_recordset(['state'])
        if operation.state not in ('dispatching', 'processing', 'reconcile'):
            return True
        detail = {'success': 'La terminal informó un resultado exitoso. Verificar el comprobante antes de conciliar.',
                  'cancelled': 'La terminal informó una cancelación. Verificar antes de liberar la operación.',
                  'uncertain': 'No se confirmó el resultado. Verificar en la terminal antes de otro intento.'}[outcome]
        operation.write({'state': 'reconcile', 'detail': detail,
                         'provider_reference': str(provider_reference or '')[:128]})
        return True
