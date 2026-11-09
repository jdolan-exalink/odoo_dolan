from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Odoo 20's pos.config inherits PosLoadMixin, whose default loader returns
    # an empty list. Keep the fields consumed by the standard POS client here
    # so custom POS fields cannot accidentally replace the core payload.
    _POS_CLIENT_FIELDS = (
        'id', 'name', 'company_id', 'currency_id', 'access_token',
        'available_preset_ids', 'available_pricelist_ids', 'cash_control',
        'cash_rounding', 'default_fiscal_position_id', 'default_preset_id',
        # pos_sale reads these relations directly while rendering order lines.
        # Some Odoo builds don't merge optional-module fields into the base
        # POS payload, so include them when that addon is installed.
        'default_product_id', 'down_payment_product_id',
        'discount_product_id', 'fast_payment_method_ids', 'fiscal_position_ids',
        'iface_available_categ_ids', 'iface_big_scrollbars',
        'iface_group_by_categ', 'iface_print_auto', 'iface_printbill',
        'iface_tax_included', 'iface_tipproduct',
        'is_margins_costs_accessible_to_every_user', 'journal_id',
        'limit_categories', 'limited_partner_ids', 'module_pos_hr',
        'module_pos_restaurant', 'only_round_cash_method', 'other_devices',
        'payment_method_ids', 'pos_snooze_ids', 'preparation_printer_ids',
        'floor_plan', 'pricelist_id', 'receipt_printer_ids', 'restrict_price_control',
        'rounding_method', 'self_ordering_mode', 'set_tip_after_payment',
        'show_category_images', 'show_product_images', 'tip_percentage_1',
        'tip_percentage_2', 'tip_percentage_3', 'tip_product_id',
        'use_download_invoice', 'use_fast_payment', 'use_presets',
        'use_pricelist', 'use_order_printer', 'trusted_config_ids',
    )

    scale_barcode_profiles = fields.Json(compute='_compute_scale_barcode_profiles')

    @api.depends('company_id', 'picking_type_id')
    def _compute_scale_barcode_profiles(self):
        Device = self.env['scale.device'].sudo()
        for config in self:
            warehouse = config.picking_type_id.warehouse_id
            devices = Device.search([
                ('company_id', '=', config.company_id.id),
                ('warehouse_id', '=', warehouse.id),
                ('active', '=', True), ('barcode_profile_id.active', '=', True),
            ]) if warehouse else Device
            profiles = {}
            for device in devices:
                profile = device.barcode_profile_id
                mapping = profiles.setdefault(profile.id, {
                    'id': profile.id, 'code': profile.code,
                    'barcode_length': profile.barcode_length,
                    'prefix': profile.prefix or '',
                    'product_start': profile.product_start,
                    'product_length': profile.product_length,
                    'value_start': profile.value_start,
                    'value_length': profile.value_length,
                    'value_type': profile.value_type,
                    'decimals': profile.decimals,
                    'check_digit': profile.check_digit,
                    'products': {},
                })
                for assignment in device.product_assignment_ids.filtered(
                    lambda line: line.active and line.assignment_type == 'product'
                    and line.disposition == 'include' and line.product_id and line.plu
                ):
                    plu = str(assignment.plu).strip()
                    previous = mapping['products'].get(plu)
                    # Ambiguous labels must fail closed. Never let device/search
                    # ordering decide which product a weighed item becomes.
                    mapping['products'][plu] = assignment.product_id.id if previous in (None, assignment.product_id.id) else False
            config.scale_barcode_profiles = list(profiles.values())

    @api.model
    def _load_pos_data_fields(self, config):
        result = list(super()._load_pos_data_fields(config) or [])
        # Filter by the runtime registry to remain compatible with optional
        # POS modules and minor changes to the Odoo 20 field set.
        for name in self._POS_CLIENT_FIELDS:
            if name in self._fields and name not in result:
                result.append(name)
        for name in ('scale_barcode_profiles',):
            if name in self._fields and name not in result:
                result.append(name)
        return result
