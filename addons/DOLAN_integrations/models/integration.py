import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STATES = [('ok', 'Bien'), ('warning', 'Revisar'), ('error', 'Error'), ('unconfigured', 'Sin configurar')]
KINDS = [
    ('arca', 'ARCA (certificado)'),
    ('whatsapp', 'WhatsApp (WAHA)'),
    ('payment_terminal', 'Terminal de cobro'),
    ('marketplace', 'Marketplace'),
    ('mail_out', 'Correo saliente'),
    ('mail_queue', 'Cola de correos'),
]


class DolanIntegrationStatus(models.Model):
    _name = 'dolan.integration.status'
    _description = 'Estado de integración'
    _order = 'state_order, kind, name'

    name = fields.Char('Integración', required=True)
    kind = fields.Selection(KINDS, 'Tipo', required=True)
    company_id = fields.Many2one('res.company', 'Empresa')
    res_model = fields.Char('Modelo', readonly=True)
    res_id = fields.Integer('ID del registro', readonly=True)
    state = fields.Selection(STATES, 'Estado', required=True, default='unconfigured')
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    message = fields.Char('Detalle')
    checked_at = fields.Datetime('Revisado', default=fields.Datetime.now)

    @api.depends('state')
    def _compute_state_order(self):
        order = {'error': 0, 'warning': 1, 'unconfigured': 2, 'ok': 3}
        for row in self:
            row.state_order = order.get(row.state, 9)

    # ------------------------------------------------------------------
    # Revisiones: cada una devuelve una lista de dicts con name, kind, state, message, company_id, res_model, res_id
    # ------------------------------------------------------------------
    @api.model
    def _check_arca(self, now):
        if 'l10n_ar_afip_ws_crt_id' not in self.env['res.company']._fields:
            return []
        rows = []
        for company in self.env['res.company'].sudo().search([('partner_id.country_id.code', '=', 'AR')]):
            cert = company.l10n_ar_afip_ws_crt_id
            env_label = getattr(company, 'l10n_ar_afip_ws_environment', '') or ''
            base = {'name': _('ARCA %(company)s %(env)s') % {'company': company.name, 'env': env_label}, 'kind': 'arca',
                    'company_id': company.id, 'res_model': 'res.company', 'res_id': company.id}
            if not cert:
                rows.append(dict(base, state='unconfigured', message=_('Sin certificado cargado.')))
            elif not cert.date_end:
                rows.append(dict(base, state='warning', message=_('No se pudo leer el vencimiento del certificado.')))
            elif cert.date_end < now:
                rows.append(dict(base, state='error', message=_('El certificado venció el %s.') % cert.date_end.strftime('%d/%m/%Y')))
            elif cert.date_end < now + timedelta(days=30):
                rows.append(dict(base, state='warning', message=_('El certificado vence el %s.') % cert.date_end.strftime('%d/%m/%Y')))
            else:
                rows.append(dict(base, state='ok', message=_('Certificado vigente hasta el %s.') % cert.date_end.strftime('%d/%m/%Y')))
        return rows

    @api.model
    def _check_whatsapp(self, now):
        if 'dolan.whatsapp.account' not in self.env:
            return []
        rows = []
        for account in self.env['dolan.whatsapp.account'].sudo().search([]):
            status = (account.session_status or '').upper()
            if status == 'WORKING':
                state, message = 'ok', _('Sesión conectada%s.') % (f' ({account.connected_phone})' if account.connected_phone else '')
            elif account.last_error:
                state, message = 'error', (account.last_error or '')[:200]
            elif status:
                state, message = 'warning', _('Sesión en estado %s.') % status
            else:
                state, message = 'unconfigured', _('Sesión sin vincular.')
            rows.append({'name': _('WhatsApp %s') % account.name, 'kind': 'whatsapp', 'company_id': account.company_id.id,
                         'state': state, 'message': message, 'res_model': account._name, 'res_id': account.id})
        return rows

    @api.model
    def _check_payment_terminals(self, now):
        if 'dolan.payment.terminal' not in self.env:
            return []
        rows = []
        for terminal in self.env['dolan.payment.terminal'].sudo().search([]):
            if terminal.provider == 'clover':
                ok = bool(terminal.clover_paired and terminal.clover_ip)
                message = _('Vinculada con Clover.') if ok else _('Falta vincular la terminal Clover.')
            else:
                ok = bool(terminal.mp_device_id or terminal.mp_external_pos_id)
                message = _('Terminal identificada.') if ok else _('Falta el identificador de la terminal o caja QR.')
            if not terminal.journal_id:
                ok, message = False, _('Falta el diario de cobro.')
            rows.append({'name': terminal.name, 'kind': 'payment_terminal', 'company_id': terminal.company_id.id,
                         'state': 'ok' if ok else 'warning', 'message': message,
                         'res_model': terminal._name, 'res_id': terminal.id})
        return rows

    @api.model
    def _check_marketplaces(self, now):
        if 'dolan.marketplace.account' not in self.env:
            return []
        rows = []
        for account in self.env['dolan.marketplace.account'].sudo().search([]):
            if account.state == 'connected':
                expired = account.token_expiry and account.token_expiry < now
                state = 'warning' if expired else 'ok'
                message = _('El token venció; se renueva en la próxima sincronización.') if expired else _('Conectada.')
            elif account.state == 'error':
                state, message = 'error', _('La última sincronización dio error.')
            else:
                state, message = 'unconfigured', _('Sin conectar.')
            rows.append({'name': account.name, 'kind': 'marketplace', 'company_id': account.company_id.id,
                         'state': state, 'message': message, 'res_model': account._name, 'res_id': account.id})
        return rows

    @api.model
    def _check_mail(self, now):
        rows = []
        servers = self.env['ir.mail_server'].sudo().search([])
        if not servers:
            rows.append({'name': _('Correo saliente'), 'kind': 'mail_out', 'state': 'unconfigured',
                         'message': _('No hay servidor de correo saliente configurado: los correos no se envían.')})
        for server in servers:
            rows.append({'name': server.name, 'kind': 'mail_out', 'state': 'ok',
                         'message': _('%(host)s:%(port)s') % {'host': server.smtp_host, 'port': server.smtp_port},
                         'res_model': server._name, 'res_id': server.id})
        failed = self.env['mail.mail'].sudo().search_count([('state', '=', 'exception')])
        rows.append({'name': _('Cola de correos'), 'kind': 'mail_queue', 'state': 'error' if failed else 'ok',
                     'message': _('%d correos con error de envío.') % failed if failed else _('Sin correos con error.')})
        return rows

    @api.model
    def _refresh(self):
        now = fields.Datetime.now()
        rows = []
        for check in (self._check_arca, self._check_whatsapp, self._check_payment_terminals, self._check_marketplaces, self._check_mail):
            try:
                rows += check(now)
            except Exception as error:  # noqa: BLE001 - una integración rota no frena el tablero
                _logger.warning('Revisión de integraciones falló en %s: %s', check.__name__, error)
                rows.append({'name': check.__name__.replace('_check_', ''), 'kind': 'mail_queue', 'state': 'error',
                             'message': str(error)[:200]})
        self.sudo().search([]).unlink()
        self.sudo().create([dict(row, checked_at=now) for row in rows])
        return len(rows)

    def action_refresh(self):
        self._refresh()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_test(self):
        """Prueba real de la conexión con el método propio de cada integración."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            raise UserError(_('Esta integración no tiene prueba de conexión.'))
        record = self.env[self.res_model].browse(self.res_id).exists()
        for method in ('action_test_connection', 'test_smtp_connection', 'action_refresh_status'):
            if record and hasattr(record, method):
                result = getattr(record, method)()
                self._refresh()
                return result
        raise UserError(_('Esta integración no tiene prueba de conexión.'))

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}
