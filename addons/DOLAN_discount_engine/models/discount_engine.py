from odoo import api, fields, models
from odoo.tools import float_round


class DolanDiscountEngine(models.AbstractModel):
    _name = 'dolan.discount.engine'
    _description = 'Evaluador determinista de descuentos DOLAN'

    @api.model
    def _evaluate_lines(self, company, pos_config, lines, payment_allocations=None, at=None):
        """Return proposals from immutable published snapshots; never mutate orders/payments."""
        at = fields.Datetime.to_datetime(at or fields.Datetime.now())
        payment_allocations = payment_allocations or []
        total_order = sum(max(0.0, float(line.get('base_amount', 0.0))) for line in lines)
        rounding = company.currency_id.rounding
        warehouse = pos_config.picking_type_id.warehouse_id if pos_config else self.env['stock.warehouse']
        versions = self.env['dolan.discount.campaign.version'].sudo().search([
            ('company_id', '=', company.id), ('valid_from', '<=', at),
            '|', ('valid_until', '=', False), ('valid_until', '>', at),
        ], order='version desc, id desc')
        versions = versions.filtered(lambda version: version._is_active_at(at, pos_config, warehouse))
        result = []

        campaign_order_totals = {}
        for line in lines:
            product = line['product']
            quantity = max(0.0, float(line.get('qty', 0.0)))
            base_amount = max(0.0, float(line.get('base_amount', 0.0)))
            if not quantity or not base_amount:
                continue
            candidates = []
            for version in versions:
                campaign = version.snapshot or {}
                for rule in campaign.get('rules', []):
                    if quantity < float(rule.get('min_qty') or 0.0):
                        continue
                    product_ids = rule.get('product_ids') or []
                    if product_ids and product.id not in product_ids:
                        continue
                    category_ids = rule.get('category_ids') or []
                    if category_ids:
                        matching = self.env['product.category'].search([('id', 'child_of', category_ids)])
                        if product.categ_id not in matching:
                            continue
                    if product.id in (rule.get('excluded_product_ids') or []):
                        continue
                    partner = line.get('partner')
                    eligible_partners = rule.get('partner_ids') or []
                    if eligible_partners and (not partner or partner.id not in eligible_partners):
                        continue
                    required_partner_categories = rule.get('partner_category_ids') or []
                    if required_partner_categories and (
                        not partner or not (set(partner.category_id.ids) & set(required_partner_categories))
                    ):
                        continue
                    ratio = 1.0
                    required_method = rule.get('payment_method_id')
                    if required_method:
                        confirmed = sum(
                            max(0.0, float(item.get('amount', 0.0)))
                            for item in payment_allocations
                            if item.get('confirmed') and item.get('payment_method_id') == required_method
                        )
                        ratio = min(1.0, confirmed / total_order) if total_order else 0.0
                    if ratio:
                        candidates.append((version, campaign, rule, ratio))

            candidates.sort(key=lambda item: (
                -int(item[2].get('priority') or 0), -int(item[1].get('priority') or 0),
                int(item[1].get('campaign_id') or 0), int(item[2].get('rule_id') or 0),
            ))
            selected = []
            for candidate in candidates:
                if not selected or (
                    bool(candidate[2].get('stackable'))
                    and all(bool(previous[2].get('stackable')) for previous in selected)
                ):
                    selected.append(candidate)
                else:
                    break

            remaining = base_amount
            for version, campaign, rule, ratio in selected:
                eligible_base = base_amount * ratio
                if rule.get('benefit_type') == 'percent':
                    amount = eligible_base * float(rule.get('benefit_value') or 0.0) / 100.0
                elif rule.get('benefit_type') == 'special_price':
                    amount = max(0.0, (float(line.get('unit_price') or 0.0) - float(rule.get('benefit_value') or 0.0)) * quantity) * ratio
                elif rule.get('benefit_type') == 'second_unit':
                    buy_qty = max(0.0, float(rule.get('buy_qty') or 0.0))
                    get_qty = max(0.0, float(rule.get('get_qty') or 0.0))
                    block = buy_qty + get_qty
                    bundles = int(quantity // block) if block else 0
                    remainder = max(0.0, quantity - bundles * block - buy_qty)
                    discounted_qty = bundles * get_qty + min(get_qty, remainder)
                    unit_price = float(line.get('unit_price') or (base_amount / quantity))
                    amount = discounted_qty * unit_price * float(rule.get('second_unit_percent') or 0.0) / 100.0 * ratio
                else:
                    amount = quantity * float(rule.get('benefit_value') or 0.0) * ratio
                amount = min(amount, float(rule.get('max_discount_amount') or amount), remaining)
                amount = max(0.0, float_round(amount, precision_rounding=rounding))
                order_cap = float(campaign.get('max_discount_per_order') or 0.0)
                if order_cap:
                    amount = min(amount, max(0.0, order_cap - campaign_order_totals.get(version.campaign_id.id, 0.0)))
                if amount:
                    result.append({
                        'line_uuid': line.get('uuid'), 'product_id': product.id,
                        'campaign_id': version.campaign_id.id,
                        'rule_id': rule.get('rule_id'), 'campaign_version': version.version,
                        'base_amount': base_amount, 'eligible_payment_ratio': ratio,
                        'discount_amount': amount, 'rule_snapshot': rule,
                        'campaign_snapshot': campaign,
                    })
                    remaining = max(0.0, remaining - amount)
                    campaign_order_totals[version.campaign_id.id] = campaign_order_totals.get(version.campaign_id.id, 0.0) + amount
        return result
