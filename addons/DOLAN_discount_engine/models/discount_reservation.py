from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DolanDiscountReservation(models.Model):
    _name = 'dolan.discount.reservation'
    _description = 'Reserva temporal de presupuesto promocional POS'
    _order = 'expires_at'

    order_uuid = fields.Char(required=True, index=True)
    session_id = fields.Many2one('pos.session', required=True, ondelete='cascade', index=True)
    config_id = fields.Many2one(related='session_id.config_id', store=True, index=True)
    company_id = fields.Many2one(related='session_id.company_id', store=True, index=True)
    expires_at = fields.Datetime(required=True, index=True)
    proposals = fields.Json(required=True, default=list)
    payment_allocations = fields.Json(default=list, copy=False)
    state = fields.Selection([('reserved', 'Reservado'), ('consumed', 'Consumido'), ('released', 'Liberado')],
                             required=True, default='reserved', index=True)

    _order_uuid_unique = models.Constraint('UNIQUE(order_uuid)', 'La reserva de esta orden ya existe.')

    @api.model
    def _cleanup_expired(self):
        reservation_model = self.sudo()
        reservation_model.search([('state', '=', 'reserved'), ('expires_at', '<=', fields.Datetime.now())]).write(
            {'state': 'released'}
        )
        retention_date = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        reservation_model.search([('state', '!=', 'reserved'), ('expires_at', '<', retention_date)]).unlink()

    @api.model
    def action_prepare_pos_order(self, session_id, order_uuid, line_data, partner_id=False, payment_method_id=False):
        """Authorize a promotion snapshot and reserve campaign budget before checkout."""
        if not isinstance(order_uuid, str) or not order_uuid or len(order_uuid) > 128:
            raise UserError(_('No se pudo identificar la orden del punto de venta.'))
        if not isinstance(line_data, list) or len(line_data) > 500:
            raise UserError(_('El detalle de la orden no es válido.'))
        session = self.env['pos.session'].browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid or session.state not in ('opened', 'closing_control'):
            raise UserError(_('La sesión de caja no está activa para este usuario.'))
        config = session.config_id
        company = session.company_id
        partner = self.env['res.partner'].sudo().browse(int(partner_id or 0)).exists()
        if partner_id and not partner:
            raise UserError(_('El cliente de la orden ya no existe. Actualizá la venta.'))
        if partner and partner.company_id and partner.company_id != company:
            raise UserError(_('El cliente no pertenece a la empresa activa de esta caja.'))
        payment_allocations = []
        if payment_method_id:
            try:
                payment_method_id = int(payment_method_id)
            except (TypeError, ValueError):
                raise UserError(_('El medio de pago elegido no es válido.'))
            if payment_method_id not in config.payment_method_ids.ids:
                raise UserError(_('El medio de pago no está habilitado en esta caja.'))
        engine_lines = []
        line_uuids = set()
        allowed_products = self.env['product.product'].sudo()
        for item in line_data:
            if not isinstance(item, dict):
                raise UserError(_('El detalle de la orden no es válido.'))
            line_uuid = str(item.get('uuid') or '')
            if not line_uuid or line_uuid in line_uuids or len(line_uuid) > 128:
                raise UserError(_('Cada línea promocionada debe tener un identificador único.'))
            line_uuids.add(line_uuid)
            product = allowed_products.browse(int(item.get('product_id') or 0)).exists()
            try:
                qty = float(item.get('qty') or 0.0)
                unit_price = float(item.get('unit_price') or 0.0)
            except (TypeError, ValueError):
                raise UserError(_('La cantidad o el precio de una línea no son válidos.'))
            if not product or product.company_id and product.company_id != company:
                raise UserError(_('Hay un producto que no pertenece a esta empresa.'))
            if qty < 0 or unit_price < 0 or qty > 100000 or unit_price > 1e12:
                raise UserError(_('La cantidad o el precio de una línea están fuera de rango.'))
            if qty and unit_price:
                engine_lines.append({
                    'uuid': line_uuid, 'product': product, 'qty': qty,
                    'base_amount': qty * unit_price, 'unit_price': unit_price, 'partner': partner,
                })

        self._cleanup_expired()
        reservation_model = self.sudo()
        existing = reservation_model.search([('order_uuid', '=', order_uuid)], limit=1)
        if existing and (existing.session_id != session or existing.state == 'consumed'):
            raise UserError(_('Esta orden ya tiene una reserva que no se puede reutilizar.'))
        at = fields.Datetime.now()
        if payment_method_id:
            order_base = sum(line['base_amount'] for line in engine_lines)
            payment_allocations = [{
                'payment_method_id': payment_method_id,
                'amount': order_base,
                # This is a server-side preauthorization before the terminal is
                # invoked. The resulting order is checked against the tender at sync.
                'confirmed': True,
            }]
        proposals = self.env['dolan.discount.engine'].sudo()._evaluate_lines(
            company, config, engine_lines, payment_allocations=payment_allocations, at=at,
        ) if engine_lines else []
        campaign_ids = sorted({item['campaign_id'] for item in proposals if item.get('campaign_id')})
        for campaign_id in campaign_ids:
            self.env.cr.execute('SELECT id FROM dolan_discount_campaign WHERE id = %s FOR UPDATE', [campaign_id])

        # Budget consumption includes active reservations, so parallel tills cannot
        # authorize the same remaining amount. Insufficient budget fails closed;
        # the checkout total is never silently changed after a payment.
        for campaign_id in campaign_ids:
            campaign = self.env['dolan.discount.campaign'].sudo().browse(campaign_id)
            if not campaign.budget_amount:
                continue
            self.env.cr.execute(
                'SELECT '
                '(SELECT COALESCE(SUM(a.discount_amount), 0) FROM dolan_discount_application a '
                ' WHERE a.campaign_id = %s AND a.state = %s) - '
                '(SELECT COALESCE(SUM(r.amount), 0) FROM dolan_discount_application_reversal r '
                ' WHERE r.campaign_id = %s)',
                [campaign_id, 'applied', campaign_id],
            )
            spent = float(self.env.cr.fetchone()[0] or 0.0)
            self.env.cr.execute(
                'SELECT COALESCE(SUM((p->>\'discount_amount\')::numeric), 0) '
                'FROM dolan_discount_reservation r, jsonb_array_elements(r.proposals) p '
                'WHERE r.state = %s AND r.expires_at > %s AND r.order_uuid != %s '
                'AND (p->>\'campaign_id\')::integer = %s',
                ['reserved', at, order_uuid, campaign_id],
            )
            reserved = float(self.env.cr.fetchone()[0] or 0.0)
            requested = sum(float(item['discount_amount']) for item in proposals if item.get('campaign_id') == campaign_id)
            if spent + reserved + requested > campaign.budget_amount + company.currency_id.rounding / 2:
                self.env['dolan.discount.alert'].sudo().log_event({
                    'name': _('Presupuesto agotado: %s') % campaign.name,
                    'company_id': company.id, 'campaign_id': campaign.id,
                    'severity': 'warning', 'category': 'budget',
                    'detail': _('Se rechazó una reserva antes del cobro porque el presupuesto disponible no alcanza.'),
                    'snapshot': {'budget': campaign.budget_amount, 'spent': spent,
                                 'reserved': reserved, 'requested': requested},
                    'actor_id': self.env.uid,
                })
                return {'status': 'budget_exhausted', 'message':
                        _('La campaña “%s” agotó su presupuesto. La promoción se quitó antes del cobro; revisá el total.') % campaign.name}

        reservation_vals = {
            'order_uuid': order_uuid, 'session_id': session.id,
            # Keep the idempotent preauthorization available through a prolonged
            # POS/network outage so a tender already accepted is not orphaned.
            'expires_at': at + timedelta(days=7), 'proposals': proposals,
            'payment_allocations': [{
                'payment_method_id': payment_method_id,
            }] if payment_method_id and any(
                (item.get('rule_snapshot') or {}).get('payment_method_id') == payment_method_id
                for item in proposals
            ) else [],
            'state': 'reserved',
        }
        reservation = existing
        if reservation:
            reservation.write(reservation_vals)
        else:
            reservation = reservation_model.create(reservation_vals)
        return {'reservation_id': reservation.id, 'expires_at': fields.Datetime.to_string(reservation.expires_at),
                'status': 'ready', 'proposals': proposals}

    @api.model
    def _consume_for_order(self, order_uuid, session, order_data=None):
        reservation = self.sudo().search([
            ('order_uuid', '=', order_uuid), ('session_id', '=', session.id),
            ('state', '=', 'reserved'), ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
        if not reservation:
            return False
        expected_methods = {
            int(item.get('payment_method_id')) for item in (reservation.payment_allocations or [])
            if item.get('payment_method_id')
        }
        if expected_methods:
            actual_methods = set()
            for command in (order_data or {}).get('payment_ids') or []:
                if not isinstance(command, (list, tuple)) or len(command) < 3 or not isinstance(command[2], dict):
                    continue
                method = command[2].get('payment_method_id')
                method = method[0] if isinstance(method, (list, tuple)) else method
                if method:
                    actual_methods.add(int(method))
            if actual_methods != expected_methods:
                raise UserError(_('El medio de pago de la venta no coincide con el que autorizó la promoción. Volvé a caja y revisá el cobro.'))
        reservation.write({'state': 'consumed'})
        return reservation.proposals
