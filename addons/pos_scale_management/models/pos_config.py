from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

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
        result = super()._load_pos_data_fields(config)
        if 'scale_barcode_profiles' not in result:
            result.append('scale_barcode_profiles')
        return result
