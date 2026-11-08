from datetime import datetime, time, timedelta
import re
import uuid

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DolanEmployeeBenefit(models.Model):
    _name = 'dolan.discount.employee.benefit'
    _description = 'Beneficio de empleado comprador'
    _order = 'name, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    partner_id = fields.Many2one('res.partner', string='Empleado beneficiario', required=True, check_company=True, ondelete='restrict', index=True)
    employee_dni = fields.Char(string='DNI', required=True, index=True, copy=False,
                               groups='DOLAN_discount_engine.group_discount_manager',
                               help='Se usa para identificar al beneficiario en caja. No se imprime en el ticket.')
    pos_config_ids = fields.Many2many('pos.config', 'dolan_discount_benefit_pos_rel', 'benefit_id', 'config_id', string='Puntos de venta', check_company=True)
    benefit_type = fields.Selection([('percent', 'Porcentaje'), ('fixed', 'Importe por compra')], required=True, default='percent')
    benefit_value = fields.Float(required=True)
    max_discount_amount = fields.Monetary(currency_field='currency_id')
    per_order_limit = fields.Monetary(currency_field='currency_id')
    daily_limit = fields.Monetary(currency_field='currency_id')
    monthly_limit = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    product_ids = fields.Many2many('product.product', 'dolan_discount_benefit_product_rel', 'benefit_id', 'product_id', string='Productos incluidos', check_company=True)
    category_ids = fields.Many2many('product.category', 'dolan_discount_benefit_category_rel', 'benefit_id', 'category_id')
    excluded_product_ids = fields.Many2many('product.product', 'dolan_discount_benefit_excluded_product_rel', 'benefit_id', 'product_id', string='Productos excluidos', check_company=True)
    date_start = fields.Date(required=True, default=fields.Date.today)
    date_end = fields.Date()
    active = fields.Boolean(default=True)
    require_approval = fields.Boolean(default=False, help='Exige la aprobación de un supervisor distinto del cajero antes de aplicar el beneficio.')
    allow_self_purchase = fields.Boolean(default=False)

    _dolan_discount_benefit_dni_company_uniq = models.Constraint(
        'UNIQUE(company_id, employee_dni)', 'El DNI debe ser único para cada compañía.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['employee_dni'] = self._normalize_dni(vals.get('employee_dni'))
        records = super().create(vals_list)
        for record in records:
            record._log_change('employee_benefit_created', {}, record._audit_snapshot())
        return records

    def write(self, vals):
        vals = dict(vals)
        if 'employee_dni' in vals:
            vals['employee_dni'] = self._normalize_dni(vals['employee_dni'])
        before = {record.id: record._audit_snapshot() for record in self}
        result = super().write(vals)
        for record in self:
            record._log_change('employee_benefit_changed', before[record.id], record._audit_snapshot())
        return result

    def _audit_snapshot(self):
        self.ensure_one()
        return {
            'benefit_id': self.id, 'partner_id': self.partner_id.id,
            'type': self.benefit_type, 'value': self.benefit_value,
            'max_discount': self.max_discount_amount, 'per_order_limit': self.per_order_limit,
            'daily_limit': self.daily_limit, 'monthly_limit': self.monthly_limit,
            'products': sorted(self.product_ids.ids), 'categories': sorted(self.category_ids.ids),
            'excluded_products': sorted(self.excluded_product_ids.ids),
            'date_start': fields.Date.to_string(self.date_start),
            'date_end': fields.Date.to_string(self.date_end) if self.date_end else False,
            'pos_configs': sorted(self.pos_config_ids.ids), 'active': self.active,
            'allow_self_purchase': self.allow_self_purchase,
        }

    def _log_change(self, event, before, after):
        self.ensure_one()
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Configuración de beneficio de empleado: %s') % self.name,
            'event': event, 'company_id': self.company_id.id,
            'actor_id': self.env.user.id, 'before_snapshot': before or {}, 'after_snapshot': after or {},
        })

    @api.constrains('benefit_value', 'benefit_type', 'date_start', 'date_end', 'max_discount_amount', 'per_order_limit', 'daily_limit', 'monthly_limit')
    def _check_benefit(self):
        for record in self:
            if record.benefit_value <= 0 or (record.benefit_type == 'percent' and record.benefit_value > 100):
                raise ValidationError(_('El beneficio debe ser positivo y el porcentaje no puede superar 100.'))
            if record.date_end and record.date_end < record.date_start:
                raise ValidationError(_('La fecha final no puede ser anterior al inicio.'))
            if any(value < 0 for value in (record.max_discount_amount, record.per_order_limit, record.daily_limit, record.monthly_limit)):
                raise ValidationError(_('Los topes no pueden ser negativos.'))

    @api.model
    def _normalize_dni(self, value):
        digits = re.sub(r'\D', '', str(value or ''))
        if not 6 <= len(digits) <= 10:
            raise ValidationError(_('Ingresá un DNI válido de entre 6 y 10 dígitos.'))
        return digits

    @api.model
    def action_apply_dni_pos(self, session_id, order_uuid, line_data, dni):
        session = self.env['pos.session'].browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid or session.state != 'opened':
            raise UserError(_('La sesión POS no está abierta para este usuario.'))
        if not isinstance(order_uuid, str) or not order_uuid or len(order_uuid) > 128:
            raise UserError(_('No se pudo identificar la orden.'))
        try:
            normalized_dni = self._normalize_dni(dni)
        except ValidationError:
            return {'status': 'invalid', 'message': _('Revisá el DNI ingresado.')}
        benefit = self.sudo().search([
            ('company_id', '=', session.company_id.id), ('employee_dni', '=', normalized_dni),
            ('active', '=', True), ('date_start', '<=', fields.Date.context_today(self)),
            '|', ('date_end', '=', False), ('date_end', '>=', fields.Date.context_today(self)),
        ], limit=1)
        if not benefit:
            return {'status': 'ineligible', 'message': _('No encontramos un beneficio vigente para ese DNI en esta empresa.')}
        if not benefit.allow_self_purchase and self.env.user.partner_id == benefit.partner_id:
            return {'status': 'self_purchase_denied', 'message': _('Este beneficio no permite compras aprobadas por el propio beneficiario.')}
        if benefit.pos_config_ids and session.config_id not in benefit.pos_config_ids:
            return {'status': 'pos_denied', 'message': _('Este beneficio no está habilitado para esta caja.')}
        try:
            normalized_lines = self._normalize_pos_lines(session, line_data)
        except (TypeError, ValueError, UserError) as error:
            return {'status': 'invalid_lines', 'message': str(error) or _('El detalle de la orden no es válido.')}
        if not normalized_lines:
            return {'status': 'no_eligible_lines', 'message': _('No hay productos en la orden que admitan este beneficio.')}
        claim = self.env['dolan.discount.employee.claim'].sudo()._reserve(
            benefit, session, order_uuid, normalized_lines,
        )
        return claim._pos_result()

    @api.model
    def _normalize_pos_lines(self, session, line_data):
        if not isinstance(line_data, list) or not line_data or len(line_data) > 500:
            raise UserError(_('El detalle de la orden no es válido.'))
        lines, seen = [], set()
        for item in line_data:
            if not isinstance(item, dict):
                raise UserError(_('El detalle de la orden no es válido.'))
            line_uuid = str(item.get('uuid') or '')
            if not line_uuid or line_uuid in seen or len(line_uuid) > 128:
                raise UserError(_('Cada línea debe tener un identificador único.'))
            seen.add(line_uuid)
            try:
                product = self.env['product.product'].sudo().browse(int(item.get('product_id') or 0)).exists()
                qty = float(item.get('qty') or 0.0)
                unit_price = float(item.get('unit_price') or 0.0)
                current_discount = float(item.get('current_discount') or 0.0)
            except (TypeError, ValueError):
                raise UserError(_('La cantidad o el precio no son válidos.'))
            if not product or (product.company_id and product.company_id != session.company_id):
                raise UserError(_('Hay un producto que no pertenece a la empresa de esta caja.'))
            if qty <= 0 or unit_price < 0 or not 0 <= current_discount <= 100:
                raise UserError(_('La cantidad, precio o descuento de una línea no son válidos.'))
            lines.append({
                'uuid': line_uuid, 'product': product, 'product_id': product.id,
                'qty': qty, 'unit_price': unit_price,
                'base_amount': qty * unit_price, 'current_discount': current_discount,
            })
        return lines


class DolanDiscountEmployeeClaim(models.Model):
    _name = 'dolan.discount.employee.claim'
    _description = 'Reserva de beneficio de empleado en POS'
    _order = 'expires_at desc'
    _check_company_auto = True

    token = fields.Char(required=True, index=True, copy=False)
    order_uuid = fields.Char(required=True, index=True, copy=False)
    session_id = fields.Many2one('pos.session', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='session_id.company_id', store=True, index=True)
    benefit_id = fields.Many2one('dolan.discount.employee.benefit', required=True, index=True, ondelete='restrict', check_company=True)
    beneficiary_id = fields.Many2one('res.partner', required=True, ondelete='restrict')
    expires_at = fields.Datetime(required=True, index=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    proposals = fields.Json(required=True, default=list)
    state = fields.Selection([
        ('pending_approval', 'Pendiente de aprobación'), ('reserved', 'Aprobado / reservado'),
        ('rejected', 'Rechazado'), ('consumed', 'Consumido'), ('released', 'Liberado'),
    ],
                             required=True, default='reserved', index=True)
    requested_by_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    rejected_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    rejection_reason = fields.Char(readonly=True, copy=False)

    _dolan_discount_employee_claim_order_uniq = models.Constraint(
        'UNIQUE(order_uuid)', 'La orden ya tiene una reserva de beneficio de empleado.',
    )
    _dolan_discount_employee_claim_token_uniq = models.Constraint(
        'UNIQUE(token)', 'El token de beneficio ya existe.',
    )

    @api.model
    def _reserve(self, benefit, session, order_uuid, lines):
        benefit = benefit.sudo()
        self.env.cr.execute('SELECT id FROM dolan_discount_employee_benefit WHERE id = %s FOR UPDATE', [benefit.id])
        existing = self.search([('order_uuid', '=', order_uuid)], limit=1)
        if existing and (existing.session_id != session or existing.state == 'consumed'):
            raise UserError(_('Esta orden ya usó o no puede reutilizar un beneficio de empleado.'))
        rounding = session.company_id.currency_id.rounding
        eligible = []
        for line in lines:
            product = line['product']
            if benefit.excluded_product_ids & product:
                continue
            if benefit.product_ids and product not in benefit.product_ids:
                continue
            if benefit.category_ids:
                categories = self.env['product.category'].search([('id', 'child_of', benefit.category_ids.ids)])
                if product.categ_id not in categories:
                    continue
            if line['base_amount'] > 0:
                if line['current_discount'] and not (existing and existing.benefit_id == benefit):
                    raise UserError(_('Quitá los descuentos manuales o de campaña de los productos elegibles antes de aplicar el beneficio.'))
                eligible.append(line)
        if not eligible:
            raise UserError(_('No hay productos elegibles para el beneficio.'))
        base_total = sum(line['base_amount'] for line in eligible)
        if benefit.benefit_type == 'percent':
            amount = base_total * benefit.benefit_value / 100.0
        else:
            amount = benefit.benefit_value
        amount = min(amount, benefit.max_discount_amount or amount, benefit.per_order_limit or amount, base_total)
        amount = session.company_id.currency_id.round(max(0.0, amount))
        if not amount:
            raise UserError(_('El beneficio no genera un descuento aplicable.'))
        now = fields.Datetime.now()
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        local_now = pytz.UTC.localize(now).astimezone(tz)
        local_day = local_now.date()
        day_start = tz.localize(datetime.combine(local_day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        day_end = tz.localize(datetime.combine(local_day + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        month_start_local = local_day.replace(day=1)
        if month_start_local.month == 12:
            month_end_local = month_start_local.replace(year=month_start_local.year + 1, month=1)
        else:
            month_end_local = month_start_local.replace(month=month_start_local.month + 1)
        month_start = tz.localize(datetime.combine(month_start_local, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        month_end = tz.localize(datetime.combine(month_end_local, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        Application = self.env['dolan.discount.application'].sudo()
        def spent(start, end):
            return sum(Application.search([
                ('employee_benefit_id', '=', benefit.id), ('source', '=', 'employee'),
                ('date_order', '>=', start), ('date_order', '<', end),
            ]).mapped('net_discount_amount'))
        existing_id = existing.id if existing else 0
        pending_domain = [('benefit_id', '=', benefit.id), ('state', 'in', ['reserved', 'pending_approval']), ('expires_at', '>', now)]
        if existing_id:
            pending_domain.append(('id', '!=', existing_id))
        pending = self.search(pending_domain)
        pending_order = sum(pending.mapped('amount'))
        if benefit.daily_limit and spent(day_start, day_end) + pending_order + amount > benefit.daily_limit + rounding / 2:
            raise UserError(_('El beneficio supera el cupo diario disponible.'))
        if benefit.monthly_limit and spent(month_start, month_end) + pending_order + amount > benefit.monthly_limit + rounding / 2:
            raise UserError(_('El beneficio supera el cupo mensual disponible.'))
        proposals, remaining = [], amount
        for line in eligible:
            share = amount * line['base_amount'] / base_total
            line_amount = min(line['base_amount'], session.company_id.currency_id.round(share), remaining)
            if line_amount > 0:
                proposals.append({
                    'line_uuid': line['uuid'], 'product_id': line['product_id'],
                    'base_amount': line['base_amount'], 'discount_amount': line_amount,
                    'benefit_id': benefit.id, 'benefit_name': benefit.name,
                })
                remaining -= line_amount
        if remaining > 0 and proposals:
            proposals[-1]['discount_amount'] += remaining
        same_approved_claim = bool(
            existing and existing.state == 'reserved' and existing.approved_by_id
            and existing.benefit_id == benefit
            and existing.amount == amount and existing.proposals == proposals
        )
        if existing and existing.state == 'rejected':
            raise UserError(_('La solicitud fue rechazada. Iniciá una nueva orden para pedir otra autorización.'))
        state = 'pending_approval' if benefit.require_approval and not same_approved_claim else 'reserved'
        values = {
            'token': existing.token if existing else str(uuid.uuid4()),
            'order_uuid': order_uuid, 'session_id': session.id, 'benefit_id': benefit.id,
            'beneficiary_id': benefit.partner_id.id, 'expires_at': now + timedelta(days=7),
            'amount': amount, 'proposals': proposals, 'state': state,
            'requested_by_id': existing.requested_by_id.id if existing else self.env.uid,
            'approved_by_id': existing.approved_by_id.id if same_approved_claim else False,
            'approved_at': existing.approved_at if same_approved_claim else False,
            'rejected_by_id': False, 'rejection_reason': False,
        }
        if existing:
            existing.write(values)
            return existing
        return self.create(values)

    def _pos_result(self):
        self.ensure_one()
        if self.state == 'pending_approval':
            return {
                'status': 'pending_approval',
                'message': _('Solicitud enviada a un supervisor. El beneficio se aplica cuando la autorice.'),
            }
        if self.state == 'rejected':
            return {'status': 'rejected', 'message': self.rejection_reason or _('La solicitud fue rechazada.')}
        return {
            'status': 'ready', 'token': self.token, 'expires_at': fields.Datetime.to_string(self.expires_at),
            'benefit_name': self.benefit_id.name, 'proposals': self.proposals,
        }

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') and not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise UserError(_('Solo un supervisor puede aprobar beneficios de empleados.'))
        self.env.cr.execute('SELECT id FROM dolan_discount_employee_claim WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state != 'pending_approval' or self.expires_at <= fields.Datetime.now():
            raise UserError(_('La solicitud ya venció o dejó de estar pendiente.'))
        if self.requested_by_id == self.env.user:
            raise UserError(_('El cajero que solicitó el beneficio no puede aprobarlo.'))
        super(DolanDiscountEmployeeClaim, self).write({
            'state': 'reserved', 'approved_by_id': self.env.user.id,
            'approved_at': fields.Datetime.now(), 'expires_at': fields.Datetime.add(fields.Datetime.now(), days=7),
        })
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Beneficio de empleado aprobado'), 'event': 'employee_benefit_approved',
            'company_id': self.company_id.id, 'actor_id': self.requested_by_id.id,
            'approved_by_id': self.env.user.id,
            'after_snapshot': {'claim_id': self.id, 'order_uuid': self.order_uuid,
                               'benefit_id': self.benefit_id.id, 'amount': self.amount},
        })
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Rechazar beneficio'),
            'res_model': 'dolan.discount.employee.claim.reject.wizard',
            'view_mode': 'form', 'target': 'new', 'context': {'default_claim_id': self.id},
        }

    def action_reject(self, reason='Rechazado por supervisor'):
        self.ensure_one()
        if not self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') and not self.env.user.has_group('DOLAN_discount_engine.group_discount_manager'):
            raise UserError(_('Solo un supervisor puede rechazar beneficios de empleados.'))
        self.env.cr.execute('SELECT id FROM dolan_discount_employee_claim WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state != 'pending_approval':
            raise UserError(_('La solicitud ya dejó de estar pendiente.'))
        if self.requested_by_id == self.env.user:
            raise UserError(_('El cajero que solicitó el beneficio no puede rechazarlo.'))
        super(DolanDiscountEmployeeClaim, self).write({
            'state': 'rejected', 'rejected_by_id': self.env.user.id,
            'rejection_reason': str(reason or '').strip()[:256] or _('Rechazado por supervisor'),
        })
        self.env['dolan.discount.audit'].sudo().create({
            'name': _('Beneficio de empleado rechazado'), 'event': 'employee_benefit_rejected',
            'company_id': self.company_id.id, 'actor_id': self.requested_by_id.id,
            'approved_by_id': self.env.user.id,
            'reason': self.rejection_reason,
            'after_snapshot': {'claim_id': self.id, 'order_uuid': self.order_uuid,
                               'benefit_id': self.benefit_id.id, 'amount': self.amount,
                               'rejected_by_id': self.env.user.id,
                               'rejection_reason': self.rejection_reason},
        })
        return True

    @api.model
    def _cleanup_expired(self):
        expired = self.sudo().search([
            ('state', 'in', ['reserved', 'pending_approval']), ('expires_at', '<=', fields.Datetime.now()),
        ])
        expired.write({'state': 'released'})
        retention = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        self.sudo().search([('state', '!=', 'reserved'), ('expires_at', '<', retention)]).unlink()
        return len(expired)

    @api.model
    def action_validate_pos_claim(self, session_id, order_uuid, token, line_data):
        session = self.env['pos.session'].browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid or session.state != 'opened':
            raise UserError(_('La sesión POS no está abierta para este usuario.'))
        claim = self.sudo().search([
            ('token', '=', str(token or '')), ('order_uuid', '=', str(order_uuid or '')),
            ('session_id', '=', session.id), ('state', 'in', ['reserved', 'pending_approval']),
            ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
        if not claim:
            raise UserError(_('La autorización del beneficio venció. Volvé a identificar al empleado.'))
        if claim.state == 'pending_approval':
            return claim._pos_result()
        lines = self.env['dolan.discount.employee.benefit']._normalize_pos_lines(session, line_data)
        renewed = self.sudo()._reserve(claim.benefit_id, session, order_uuid, lines)
        if renewed.token != claim.token:
            renewed.write({'token': claim.token})
        return renewed._pos_result()

    @api.model
    def action_release_pos_claim(self, session_id, order_uuid, token):
        session = self.env['pos.session'].browse(int(session_id or 0)).exists()
        if not session or session.user_id.id != self.env.uid:
            raise UserError(_('La sesión no corresponde al usuario.'))
        claim = self.sudo().search([
            ('token', '=', str(token or '')), ('order_uuid', '=', str(order_uuid or '')),
            ('session_id', '=', session.id), ('state', 'in', ['reserved', 'pending_approval']),
        ], limit=1)
        if claim:
            claim.write({'state': 'released'})
        return True

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_('Las solicitudes de beneficio solo cambian desde las acciones autorizadas.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise ValidationError(_('Las reservas de beneficio se conservan para auditoría.'))
        return super().unlink()


class DolanDiscountEmployeeClaimRejectWizard(models.TransientModel):
    _name = 'dolan.discount.employee.claim.reject.wizard'
    _description = 'Rechazar beneficio de empleado'

    claim_id = fields.Many2one('dolan.discount.employee.claim', required=True, readonly=True)
    reason = fields.Char(required=True, default='Solicitud rechazada por supervisor')

    def action_confirm(self):
        self.ensure_one()
        if not self.reason.strip():
            raise ValidationError(_('Indicá el motivo del rechazo.'))
        self.claim_id.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
