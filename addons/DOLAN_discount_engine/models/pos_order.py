from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    dolan_discount_base_percent = fields.Float(copy=False, digits=0)
    dolan_discount_applications = fields.Json(copy=False, default=list)
    dolan_discount_reason = fields.Char(copy=False)
    dolan_discount_approval_uuid = fields.Char(copy=False)
    dolan_discount_employee_token = fields.Char(copy=False)
    dolan_discount_employee_applications = fields.Json(copy=False, default=list)

    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        for name in ('dolan_discount_base_percent', 'dolan_discount_applications', 'dolan_discount_reason',
                     'dolan_discount_approval_uuid', 'dolan_discount_employee_token',
                     'dolan_discount_employee_applications'):
            if name not in result:
                result.append(name)
        return result


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, existing_order):
        session = self.env['pos.session'].browse(order.get('session_id')).exists()
        config = session.config_id if session else self.env['pos.config']
        company = config.company_id if config else self.env['res.company']
        line_commands = order.get('lines') or []
        lines_by_uuid = {}
        engine_lines = []
        employee_tokens = set()

        # POS serializes lines as (operation, id, values). Only line values that
        # requested an automatic campaign in the UI are considered here. Rule IDs
        # and amounts from the browser are never trusted; the engine recalculates.
        for command in line_commands:
            if not isinstance(command, (list, tuple)) or len(command) < 3 or not isinstance(command[2], dict):
                continue
            values = command[2]
            if values.get('dolan_discount_applications') and not values.get('uuid'):
                raise UserError(_('No se pudo identificar una línea promocionada. Volvé a la venta y sincronizala.'))
            product_id = values.get('product_id')
            product_id = product_id[0] if isinstance(product_id, (list, tuple)) else product_id
            product = self.env['product.product'].browse(product_id).exists()
            if not product:
                values['dolan_discount_applications'] = []
                continue
            quantity = max(0.0, float(values.get('qty') or 0.0))
            base_amount = max(0.0, quantity * float(values.get('price_unit') or 0.0))
            line_uuid = values.get('uuid')
            if line_uuid:
                lines_by_uuid[line_uuid] = values
            if values.get('dolan_discount_employee_token'):
                employee_tokens.add(values['dolan_discount_employee_token'])
            if values.get('dolan_discount_applications') and line_uuid and quantity and base_amount:
                engine_lines.append({
                    'uuid': line_uuid, 'product': product, 'qty': quantity,
                    'base_amount': base_amount, 'unit_price': float(values.get('price_unit') or 0.0),
                })

        # Automatic benefits and their budgets must have been authorized and
        # reserved by the server before POS entered its payment screen. Never
        # recalculate or reduce a discount after a card/QR terminal may have paid.
        proposals = self.env['dolan.discount.reservation']._consume_for_order(
            order.get('uuid') or '', session, order,
        ) if session and order.get('uuid') else False
        client_requested_campaign = any(values.get('dolan_discount_applications') for values in lines_by_uuid.values())
        if client_requested_campaign and proposals is False:
            raise UserError(_('La autorización de promociones venció. Volvé a la venta y presioná Cobrar nuevamente.'))
        proposals = proposals or []
        employee_by_uuid = {}
        employee_claim = False
        if employee_tokens:
            if len(employee_tokens) != 1 or not session or not order.get('uuid'):
                raise UserError(_('La autorización del beneficio de empleado no coincide con la orden.'))
            employee_token = next(iter(employee_tokens))
            employee_values = [values for values in lines_by_uuid.values()
                               if values.get('dolan_discount_employee_token') == employee_token]
            employee_line_data = [{
                'uuid': values.get('uuid'),
                'product_id': (values.get('product_id') or [False])[0] if isinstance(values.get('product_id'), (list, tuple)) else values.get('product_id'),
                'qty': values.get('qty'), 'unit_price': values.get('price_unit'),
                'current_discount': 0.0,
            } for values in employee_values]
            employee_result = self.env['dolan.discount.employee.claim'].action_validate_pos_claim(
                session.id, order.get('uuid'), employee_token, employee_line_data,
            )
            employee_claim = self.env['dolan.discount.employee.claim'].sudo().search([
                ('token', '=', employee_token), ('order_uuid', '=', order.get('uuid')),
                ('session_id', '=', session.id), ('state', '=', 'reserved'),
            ], limit=1)
            if not employee_claim:
                raise UserError(_('La reserva de beneficio de empleado ya no está vigente.'))
            employee_by_uuid = {item['line_uuid']: item for item in employee_result.get('proposals', [])}
            client_employee = {
                values.get('uuid'): (values.get('dolan_discount_employee_applications') or [])
                for values in employee_values
            }
            if set(employee_by_uuid) != set(client_employee):
                raise UserError(_('El beneficio de empleado cambió después de su validación. Volvé a caja y recalculalo.'))
            for line_uuid, expected in employee_by_uuid.items():
                client_items = client_employee[line_uuid]
                if len(client_items) != 1 or abs(float(client_items[0].get('discount_amount') or 0.0)
                                                 - float(expected['discount_amount'])) > company.currency_id.rounding / 2:
                    raise UserError(_('El importe del beneficio de empleado no coincide con la autorización del servidor.'))
                values = lines_by_uuid[line_uuid]
                base = max(0.0, float(values.get('qty') or 0.0) * float(values.get('price_unit') or 0.0))
                expected_percent = 100.0 * float(expected['discount_amount']) / base if base else 0.0
                if abs(float(values.get('discount') or 0.0) - expected_percent) > 0.0001:
                    raise UserError(_('La línea cambió después de aplicar el beneficio de empleado. Volvé a recalcularla.'))
                employee_by_uuid[line_uuid] = expected
        reserved_by_uuid = {}
        for item in proposals:
            reserved_by_uuid.setdefault(item.get('line_uuid'), []).append(item)
        client_promo_uuids = {
            line_uuid for line_uuid, values in lines_by_uuid.items()
            if values.get('dolan_discount_applications')
        }
        if client_promo_uuids != set(reserved_by_uuid):
            raise UserError(_('Las promociones de la venta no coinciden con la autorización previa. Volvé a la venta y recalculala.'))
        for line_uuid, reserved in reserved_by_uuid.items():
            values = lines_by_uuid.get(line_uuid)
            if not values:
                raise UserError(_('La orden cambió después de autorizar la promoción. Volvé a la venta y recalculala.'))
            product_id = values.get('product_id')
            product_id = product_id[0] if isinstance(product_id, (list, tuple)) else product_id
            base = max(0.0, float(values.get('qty') or 0.0) * float(values.get('price_unit') or 0.0))
            expected_base = float(reserved[0].get('base_amount') or 0.0)
            if not reserved or product_id != reserved[0].get('product_id') or abs(base - expected_base) > company.currency_id.rounding:
                raise UserError(_('La línea cambió después de autorizar la promoción. Volvé a la venta y recalculala.'))
            client_items = values.get('dolan_discount_applications') or []
            reserved_keys = {
                (item.get('campaign_id'), item.get('rule_id'), item.get('campaign_version')): float(item.get('discount_amount') or 0.0)
                for item in reserved
            }
            client_keys = {
                (item.get('campaign_id'), item.get('rule_id'), item.get('campaign_version')): float(item.get('discount_amount') or 0.0)
                for item in client_items
            }
            if reserved_keys.keys() != client_keys.keys() or any(
                abs(reserved_keys[key] - client_keys[key]) > company.currency_id.rounding / 2
                for key in reserved_keys
            ):
                raise UserError(_('El descuento no coincide con la reserva del servidor. Volvé a la venta y recalculala.'))
            promo_amount = sum(reserved_keys.values())
            base_discount = max(0.0, min(100.0, float(values.get('dolan_discount_base_percent') or 0.0)))
            promo_percent = min(100.0, promo_amount * 100.0 / base) if base else 0.0
            expected_discount = 100.0 * (1.0 - (1.0 - base_discount / 100.0) * (1.0 - promo_percent / 100.0))
            if abs(float(values.get('discount') or 0.0) - expected_discount) > 0.0001:
                raise UserError(_('El total de la línea cambió después de autorizarla. Volvé a la venta y recalculala.'))
            values['dolan_discount_applications'] = reserved
        for line_uuid, values in lines_by_uuid.items():
            # Automatic campaigns are deliberately exclusive with native/manual
            # line discounts in this first POS slice. Never trust a client supplied
            # base percentage as authority to increase a campaign discount.
            client_has_campaign_preview = bool(values.get('dolan_discount_applications'))
            has_employee_benefit = line_uuid in employee_by_uuid
            original_discount = max(0.0, min(100.0, float(
                values.get('dolan_discount_base_percent') if client_has_campaign_preview or has_employee_benefit
                else values.get('discount') or 0.0
            )))
            # Manual discounts and campaign discounts are mutually exclusive. A
            # client cannot forge a 100% base discount next to a valid campaign.
            applications = [] if original_discount or has_employee_benefit else reserved_by_uuid.get(line_uuid, [])
            base = max(0.0, float(values.get('qty') or 0.0) * float(values.get('price_unit') or 0.0))
            promo_amount = sum(item['discount_amount'] for item in applications)
            promo_percent = min(100.0, promo_amount * 100.0 / base) if base else 0.0
            if has_employee_benefit:
                values['discount'] = 100.0 * employee_by_uuid[line_uuid]['discount_amount'] / base if base else 0.0
            else:
                values['discount'] = 100.0 * (1.0 - (1.0 - original_discount / 100.0) * (1.0 - promo_percent / 100.0))
            values['dolan_discount_base_percent'] = original_discount
            values['dolan_discount_applications'] = applications

            # A discount carried in the native line field without a campaign is a
            # manual/native discount. Require an enabled per-POS ceiling, an
            # independent supervisor for higher values, and an audit reason.
            native_discount = original_discount
            if native_discount and float(values.get('qty') or 0.0) > 0:
                allowed = float(getattr(config, 'dolan_discount_cashier_limit', 0.0) or 0.0)
                supervisor = self.env.user.has_group('DOLAN_discount_engine.group_discount_supervisor') or self.env.user.has_group('DOLAN_discount_engine.group_discount_manager')
                manager = self.env.user.has_group('DOLAN_discount_engine.group_discount_manager')
                if supervisor and not manager:
                    allowed = float(getattr(config, 'dolan_discount_supervisor_limit', 100.0) or 0.0)
                if native_discount > allowed:
                    approval = self.env['dolan.discount.approval'].sudo().search([
                        ('request_uuid', '=', values.get('dolan_discount_approval_uuid')),
                    ], limit=1)
                    if not approval:
                        raise UserError(_('Este descuento necesita una autorización aprobada por otro usuario.'))
                    approval.consume_for_pos(order.get('uuid') or '', line_uuid or '', native_discount)
                if not values.get('dolan_discount_reason'):
                    raise UserError(_('Indicá un motivo para registrar el descuento manual.'))
                values['dolan_discount_applications'] = []

        order_id = super()._process_order(order, existing_order)
        if order.get('state') != 'draft':
            pos_order = self.browse(order_id)
            if employee_claim:
                employee_claim.write({'state': 'consumed'})
            for line_uuid, values in lines_by_uuid.items():
                line = pos_order.lines.filtered(lambda item: item.uuid == line_uuid)[:1]
                if not line:
                    continue
                employee_application = employee_by_uuid.get(line_uuid)
                if employee_application:
                    benefit = employee_claim.benefit_id
                    if not self.env['dolan.discount.application'].sudo().search_count([
                        ('order_line_id', '=', line.id), ('employee_benefit_id', '=', benefit.id),
                        ('source', '=', 'employee'),
                    ]):
                        self.env['dolan.discount.application'].sudo().create({
                            'order_id': pos_order.id, 'order_line_id': line.id,
                            'employee_benefit_id': benefit.id, 'campaign_version': 0,
                            'base_amount': employee_application['base_amount'],
                            'eligible_payment_ratio': 1.0,
                            'discount_amount': employee_application['discount_amount'],
                            'rule_snapshot': {'name': _('Beneficio de empleado'),
                                              'benefit_name': benefit.name},
                            'campaign_snapshot': {}, 'source': 'employee',
                            'actor_id': self.env.user.id,
                            'applied_subtotal': line.price_subtotal,
                            'tax_amount': line.price_subtotal_incl - line.price_subtotal,
                            'total_after_discount': line.price_subtotal_incl,
                        })
                        self.env['dolan.discount.audit'].sudo().create({
                            'name': _('Beneficio de empleado aplicado'), 'event': 'employee_benefit_used',
                            'company_id': pos_order.company_id.id, 'order_id': pos_order.id,
                            'order_line_id': line.id, 'actor_id': self.env.user.id,
                            'after_snapshot': {'benefit_id': benefit.id,
                                               'amount': employee_application['discount_amount']},
                        })
                if line.qty > 0 and line.discount and not employee_application and not (values.get('dolan_discount_applications') or []):
                    existing_manual_audit = self.env['dolan.discount.audit'].sudo().search_count([
                        ('order_line_id', '=', line.id), ('event', '=', 'manual_discount_applied'),
                    ])
                    if not existing_manual_audit:
                        self.env['dolan.discount.audit'].sudo().create({
                            'name': _('Descuento manual aplicado'), 'event': 'manual_discount_applied',
                            'company_id': pos_order.company_id.id, 'order_id': pos_order.id,
                            'order_line_id': line.id, 'actor_id': self.env.user.id,
                            'after_snapshot': {'discount_percent': line.discount,
                                               'discount_amount': line.qty * line.price_unit * line.discount / 100.0},
                            'reason': (values.get('dolan_discount_reason') or '')[:256],
                        })
                    if not self.env['dolan.discount.application'].sudo().search_count([
                        ('order_line_id', '=', line.id), ('source', '=', 'manual'),
                    ]):
                        approval = self.env['dolan.discount.approval'].sudo().search([
                            ('request_uuid', '=', values.get('dolan_discount_approval_uuid')),
                            ('state', '=', 'used'),
                        ], limit=1)
                        base_amount = max(0.0, line.qty * line.price_unit)
                        self.env['dolan.discount.application'].sudo().create({
                            'order_id': pos_order.id, 'order_line_id': line.id,
                            'campaign_version': 0, 'base_amount': base_amount,
                            'eligible_payment_ratio': 1.0,
                            'discount_amount': base_amount * line.discount / 100.0,
                            'rule_snapshot': {'name': _('Descuento manual'),
                                              'discount_percent': line.discount,
                                              'reason': values.get('dolan_discount_reason') or ''},
                            'campaign_snapshot': {}, 'source': 'manual',
                            'actor_id': self.env.user.id,
                            'approved_by_id': approval.approved_by_id.id or False,
                            'applied_subtotal': line.price_subtotal,
                            'tax_amount': line.price_subtotal_incl - line.price_subtotal,
                            'total_after_discount': line.price_subtotal_incl,
                        })
                for item in values.get('dolan_discount_applications') or []:
                    if self.env['dolan.discount.application'].sudo().search_count([
                        ('order_line_id', '=', line.id), ('campaign_id', '=', item['campaign_id']),
                        ('rule_id', '=', item['rule_id']), ('campaign_version', '=', item['campaign_version']),
                    ]):
                        continue
                    self.env['dolan.discount.application'].sudo().create({
                        'order_id': pos_order.id,
                        'order_line_id': line.id,
                        'campaign_id': item['campaign_id'],
                        'rule_id': self.env['dolan.discount.rule'].browse(item['rule_id']).exists().id or False,
                        'campaign_version': item['campaign_version'],
                        'base_amount': item['base_amount'],
                        'eligible_payment_ratio': item['eligible_payment_ratio'],
                        'discount_amount': item['discount_amount'],
                        'rule_snapshot': item['rule_snapshot'],
                        'campaign_snapshot': item['campaign_snapshot'],
                        'applied_subtotal': line.price_subtotal,
                        'tax_amount': line.price_subtotal_incl - line.price_subtotal,
                        'total_after_discount': line.price_subtotal_incl,
                        'source': 'campaign',
                        'actor_id': self.env.user.id,
                    })
                    self.env['dolan.discount.audit'].sudo().create({
                        'name': 'Promoción aplicada: %s' % (item['rule_snapshot'].get('name') or ''),
                        'event': 'discount_applied', 'company_id': pos_order.company_id.id,
                        'campaign_id': item['campaign_id'], 'order_id': pos_order.id,
                        'order_line_id': line.id, 'actor_id': self.env.user.id,
                        'after_snapshot': {'rule_id': item['rule_id'], 'version': item['campaign_version'],
                                           'amount': item['discount_amount'], 'base': item['base_amount']},
                    })
            if 'refunded_orderline_id' in self.env['pos.order.line']._fields:
                reversal_model = self.env['dolan.discount.application.reversal'].sudo()
                for refund_line in pos_order.lines.filtered('refunded_orderline_id'):
                    original_line = refund_line.refunded_orderline_id
                    original_qty = abs(original_line.qty)
                    returned_qty = abs(refund_line.qty)
                    if not original_qty or not returned_qty:
                        continue
                    applications = self.env['dolan.discount.application'].sudo().search([
                        ('order_line_id', '=', original_line.id), ('state', '=', 'applied'),
                    ])
                    for application in applications:
                        if reversal_model.search_count([
                            ('application_id', '=', application.id),
                            ('refund_order_line_id', '=', refund_line.id),
                        ]):
                            continue
                        ratio = min(1.0, returned_qty / original_qty)
                        previous = reversal_model.search([('application_id', '=', application.id)])
                        already_reversed = sum(item.amount for item in previous)
                        target_reversed = application.currency_id.round(application.discount_amount * min(
                            1.0, ratio + sum(item.quantity_ratio for item in previous),
                        ))
                        amount = max(0.0, target_reversed - already_reversed)
                        if not amount:
                            continue
                        reversal_model.create({
                            'application_id': application.id, 'refund_order_id': pos_order.id,
                            'refund_order_line_id': refund_line.id, 'amount': amount,
                            'quantity_ratio': ratio, 'actor_id': self.env.user.id,
                            'reason': _('Devolución POS %s') % (pos_order.pos_reference or pos_order.name),
                        })
                        self.env['dolan.discount.audit'].sudo().create({
                            'name': _('Descuento revertido proporcionalmente por devolución'),
                            'event': 'discount_reversed', 'company_id': application.company_id.id,
                            'campaign_id': application.campaign_id.id, 'order_id': pos_order.id,
                            'order_line_id': refund_line.id, 'actor_id': application.actor_id.id,
                            'approved_by_id': self.env.user.id,
                            'before_snapshot': {'discount_amount': application.discount_amount,
                                                'campaign_version': application.campaign_version},
                            'after_snapshot': {'reversal_amount': amount, 'quantity_ratio': ratio,
                                               'refund_line_id': refund_line.id},
                            'reason': _('Devolución POS'),
                        })
        return order_id


class PosOrderReceipt(models.AbstractModel):
    _inherit = 'pos.order.receipt'

    def _order_receipt_generate_line_data(self):
        lines = super()._order_receipt_generate_line_data()
        source_lines = {line.id: line for line in self.lines}
        for data in lines:
            line = source_lines.get(data.get('id'))
            data['dolan_promotions'] = []
            if not line:
                continue
            for application in line.dolan_discount_applications or []:
                amount = max(0.0, float(application.get('discount_amount') or 0.0))
                if amount:
                    data['dolan_promotions'].append({
                        'label': _('Promoción'),
                        'amount': self._order_receipt_format_currency(amount, self.currency_id),
                    })
            if line.discount and not data['dolan_promotions']:
                manual_amount = max(0.0, line.qty * line.price_unit * line.discount / 100.0)
                if manual_amount:
                    data['dolan_promotions'].append({
                        'label': _('Descuento'),
                        'amount': self._order_receipt_format_currency(manual_amount, self.currency_id),
                    })
        return lines
