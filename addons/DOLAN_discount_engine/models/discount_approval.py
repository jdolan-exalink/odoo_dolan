import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanDiscountApproval(models.Model):
    _name = 'dolan.discount.approval'
    _description = 'Autorización puntual de descuento POS'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _('Solicitud de autorización'))
    request_uuid = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), copy=False, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='restrict')
    pos_config_id = fields.Many2one('pos.config', required=True, check_company=True, ondelete='restrict')
    order_uuid = fields.Char(required=True, index=True)
    line_uuid = fields.Char(required=True, index=True)
    product_id = fields.Many2one('product.product', required=True, check_company=True, ondelete='restrict')
    requested_by_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='restrict')
    approved_by_id = fields.Many2one('res.users', readonly=True, ondelete='restrict')
    requested_discount = fields.Float(required=True)
    authorized_discount = fields.Float(readonly=True)
    requested_reason = fields.Char(required=True)
    state = fields.Selection([
        ('pending', 'Pendiente'), ('approved', 'Aprobada'), ('rejected', 'Rechazada'),
        ('used', 'Usada'), ('expired', 'Vencida'),
    ], required=True, default='pending', index=True)
    expires_at = fields.Datetime(required=True, default=lambda self: fields.Datetime.add(fields.Datetime.now(), minutes=5))
    approved_at = fields.Datetime(readonly=True)
    used_at = fields.Datetime(readonly=True)
    used_order_uuid = fields.Char(readonly=True)
    _request_uuid_uniq = models.Constraint('UNIQUE(request_uuid)', 'La solicitud de autorización debe ser única.')

    @api.model_create_multi
    def create(self, vals_list):
        clean_vals = []
        for incoming in vals_list:
            vals = dict(incoming)
            config = self.env['pos.config'].browse(vals.get('pos_config_id')).exists()
            if not config or config.company_id.id != vals.get('company_id') or config.company_id not in self.env.companies:
                raise AccessError(_('La caja no pertenece a una empresa habilitada para el usuario.'))
            vals.update({
                'requested_by_id': self.env.user.id,
                'state': 'pending',
                'approved_by_id': False,
                'authorized_discount': 0.0,
                'approved_at': False,
                'used_at': False,
                'used_order_uuid': False,
                # Give the supervisor time to reach the POS even if the tills
                # briefly lose connectivity. Approved requests are bound to one
                # exact order/line and are single-use.
                'expires_at': fields.Datetime.add(fields.Datetime.now(), minutes=30),
            })
            clean_vals.append(vals)
        records = super().create(clean_vals)
        for record in records:
            self.env['dolan.discount.audit'].sudo().create({
                'name': _('Solicitud de descuento excepcional'), 'event': 'approval_requested',
                'company_id': record.company_id.id, 'actor_id': record.requested_by_id.id,
                'after_snapshot': {'request_uuid': record.request_uuid, 'line_uuid': record.line_uuid,
                                   'requested_discount': record.requested_discount,
                                   'product_id': record.product_id.id},
                'reason': record.requested_reason,
            })
        return records

    @api.constrains('requested_discount')
    def _check_requested_discount(self):
        if any(not 0 < record.requested_discount <= 100 for record in self):
            raise ValidationError(_('El descuento solicitado debe estar entre 0 y 100 por ciento.'))

    @api.model
    def action_prepare_pos_discount(self, session_id, order_uuid, line_uuid, product_id,
                                    discount_percent, reason, request_uuid=False):
        """Check manual discount policy and create/reuse an independent approval request."""
        session = self.env['pos.session'].browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid or session.state != 'opened':
            raise AccessError(_('La sesión de caja no está activa para este usuario.'))
        try:
            discount_percent = float(discount_percent)
            product_id = int(product_id)
        except (TypeError, ValueError):
            raise UserError(_('El descuento manual no es válido.'))
        reason = (reason or '').strip()[:256]
        if not order_uuid or not line_uuid or not reason or not 0 < discount_percent <= 100:
            raise UserError(_('Indicá un motivo y un descuento válido para continuar.'))
        product = self.env['product.product'].sudo().browse(product_id).exists()
        if not product or (product.company_id and product.company_id != session.company_id):
            raise AccessError(_('El producto no pertenece a la empresa de esta caja.'))
        supervisor = self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor')
        manager = self.env.user.has_group('DOLAN_discount_engine.group_discount_manager')
        if manager:
            allowed = 100.0
        elif supervisor:
            allowed = float(session.config_id.dolan_discount_supervisor_limit or 0.0)
        else:
            allowed = float(session.config_id.dolan_discount_cashier_limit or 0.0)
        if discount_percent <= allowed:
            return {'status': 'authorized', 'request_uuid': False}
        if request_uuid:
            approval = self.sudo().search([
                ('request_uuid', '=', request_uuid), ('order_uuid', '=', order_uuid),
                ('line_uuid', '=', line_uuid), ('product_id', '=', product_id),
                ('requested_by_id', '=', self.env.uid),
            ], limit=1)
            if approval and approval.state == 'approved' and approval.expires_at > fields.Datetime.now() \
                    and approval.authorized_discount + 1e-6 >= discount_percent:
                return {'status': 'authorized', 'request_uuid': approval.request_uuid}
            if (approval and approval.state == 'pending' and approval.expires_at > fields.Datetime.now()
                    and abs(approval.requested_discount - discount_percent) < 1e-6):
                return {'status': 'pending', 'request_uuid': approval.request_uuid}
        existing = self.sudo().search([
            ('order_uuid', '=', order_uuid), ('line_uuid', '=', line_uuid),
            ('requested_by_id', '=', self.env.uid), ('state', '=', 'pending'),
            ('expires_at', '>', fields.Datetime.now()), ('requested_discount', '=', discount_percent),
        ], limit=1)
        if existing:
            return {'status': 'pending', 'request_uuid': existing.request_uuid}
        approval = self.sudo().create({
            'company_id': session.company_id.id, 'pos_config_id': session.config_id.id,
            'order_uuid': order_uuid, 'line_uuid': line_uuid, 'product_id': product_id,
            'requested_discount': discount_percent, 'requested_reason': reason,
        })
        return {'status': 'pending', 'request_uuid': approval.request_uuid}

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') and not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise AccessError(_('Solo un supervisor o administrador puede autorizar descuentos.'))
        if self.requested_by_id == self.env.user:
            raise AccessError(_('La persona que solicita el descuento no puede autorizarlo.'))
        if self.state != 'pending' or self.expires_at <= fields.Datetime.now():
            raise UserError(_('La solicitud ya venció o dejó de estar pendiente.'))
        super(DolanDiscountApproval, self).write({
            'state': 'approved', 'approved_by_id': self.env.user.id,
            'authorized_discount': self.requested_discount, 'approved_at': fields.Datetime.now(),
            'expires_at': fields.Datetime.add(fields.Datetime.now(), days=7),
        })
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Descuento autorizado'), 'event': 'approval_granted',
            'company_id': self.company_id.id, 'actor_id': self.requested_by_id.id,
            'approved_by_id': self.env.user.id,
            'after_snapshot': {'request_uuid': self.request_uuid, 'line_uuid': self.line_uuid,
                               'discount': self.authorized_discount, 'reason': self.requested_reason},
            'reason': self.requested_reason,
        })
        return True

    def action_reject(self, reason):
        self.ensure_one()
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') and not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise AccessError(_('Solo un supervisor o administrador puede rechazar descuentos.'))
        if self.requested_by_id == self.env.user:
            raise AccessError(_('La persona que solicita no puede autorizar ni rechazar su propia excepción.'))
        if not reason or not reason.strip():
            raise UserError(_('Indicá un motivo para rechazar la solicitud.'))
        if self.state != 'pending':
            raise UserError(_('La solicitud ya dejó de estar pendiente.'))
        super(DolanDiscountApproval, self).write({'state': 'rejected', 'approved_by_id': self.env.user.id,
                                                  'approved_at': fields.Datetime.now()})
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Descuento rechazado'), 'event': 'approval_rejected',
            'company_id': self.company_id.id, 'actor_id': self.requested_by_id.id,
            'approved_by_id': self.env.user.id,
            'after_snapshot': {'request_uuid': self.request_uuid, 'line_uuid': self.line_uuid,
                               'requested_discount': self.requested_discount},
            'reason': reason.strip()[:256],
        })
        return True

    def consume_for_pos(self, order_uuid, line_uuid, discount_percent):
        """Validate and consume one approved exception inside the order transaction."""
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM dolan_discount_approval WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if (self.state != 'approved' or self.expires_at <= fields.Datetime.now()
                or self.order_uuid != order_uuid or self.line_uuid != line_uuid
                or self.company_id not in self.env.companies
                or self.requested_by_id != self.env.user
                or self.authorized_discount + 1e-6 < float(discount_percent)):
            raise UserError(_('La autorización no corresponde a esta operación, venció o ya fue utilizada.'))
        if self.approved_by_id == self.requested_by_id or self.approved_by_id == self.env.user:
            raise AccessError(_('La aprobación debe pertenecer a un supervisor distinto del cajero.'))
        super(DolanDiscountApproval, self).write({
            'state': 'used', 'used_at': fields.Datetime.now(), 'used_order_uuid': order_uuid,
        })
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Autorización utilizada en POS'), 'event': 'approval_used',
            'company_id': self.company_id.id, 'actor_id': self.requested_by_id.id,
            'approved_by_id': self.approved_by_id.id,
            'after_snapshot': {'request_uuid': self.request_uuid, 'order_uuid': order_uuid,
                               'line_uuid': line_uuid, 'discount_percent': discount_percent},
            'reason': self.requested_reason,
        })
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') and not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise AccessError(_('Solo un supervisor o administrador puede rechazar descuentos.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar solicitud'),
            'res_model': 'dolan.discount.approval.reject.wizard',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_approval_id': self.id},
        }

    def write(self, vals):
        raise UserError(_('Una solicitud emitida solo puede cambiar mediante una acción de aprobación.'))

    def unlink(self):
        raise UserError(_('Las solicitudes se conservan para auditoría.'))
