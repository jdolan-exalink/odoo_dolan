from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ScaleExportProfile(models.Model):
    _name = 'scale.export.profile'
    _description = 'Perfil de exportación de balanzas'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    brand = fields.Selection(
        [('kretz', 'Kretz'), ('other', 'Otra marca')],
        required=True,
        default='kretz',
    )
    adapter_code = fields.Char(required=True, default='kretz_itegra', readonly=True)
    format_version = fields.Char(string='Versión de formato')
    validation_state = fields.Selection(
        [('draft', 'Borrador'), ('in_validation', 'En validación'), ('validated', 'Validado')],
        default='draft', required=True,
    )
    evidence_attachment_id = fields.Many2one('ir.attachment', string='Archivo de referencia aceptado')
    itegra_version = fields.Char(string='Versión de iTegra')
    validation_note = fields.Text(string='Evidencia y resultado de prueba')
    validated_at = fields.Datetime(readonly=True, copy=False)
    validated_by = fields.Many2one('res.users', readonly=True, copy=False)
    price_tax_mode = fields.Selection(
        [('tax_excluded', 'Precio sin impuestos'), ('tax_included', 'Precio con impuestos')],
        default='tax_excluded', required=True,
        help='Debe confirmarse para el formato real antes de habilitar exportaciones.',
    )
    weight_unit = fields.Selection(
        [('kg', 'Kilogramo'), ('g', 'Gramo')], default='kg', required=True,
    )
    price_decimals = fields.Integer(default=2, required=True)
    price_rounding = fields.Float(default=0.01, required=True)
    requires_plu = fields.Boolean(default=True)
    max_plu_length = fields.Integer(default=0, help='0 indica que aún no se conoce.')
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _scale_export_profile_code_uniq = models.Constraint(
        'UNIQUE(code)',
        'El código del perfil debe ser único.',
    )
    _scale_export_profile_decimals_check = models.Constraint(
        'CHECK(price_decimals >= 0 AND price_decimals <= 6)',
        'La precisión debe estar entre 0 y 6 decimales.',
    )
    _scale_export_profile_rounding_check = models.Constraint(
        'CHECK(price_rounding > 0)',
        'El redondeo debe ser mayor que cero.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('validation_state') == 'validated' or vals.get('validated_at') or vals.get('validated_by'):
                raise UserError(_('Un perfil nuevo siempre comienza en borrador y no puede traer validación previa.'))
            vals['validation_state'] = 'draft'
            vals.pop('validated_at', None)
            vals.pop('validated_by', None)
        return super().create(vals_list)

    def write(self, vals):
        protected = {'validation_state', 'validated_at', 'validated_by', 'adapter_code'}
        if protected.intersection(vals):
            raise UserError(_('El adaptador y la validación solo cambian desde las acciones del perfil.'))
        return super().write(vals)

    def action_start_validation(self):
        self.ensure_one()
        if not self.env.user.has_group('pos_scale_management.group_scale_admin'):
            raise UserError(_('Solo un administrador de balanzas puede cambiar el estado de validación.'))
        super(ScaleExportProfile, self).write({'validation_state': 'in_validation'})

    def action_mark_validated(self):
        self.ensure_one()
        if not self.env.user.has_group('pos_scale_management.group_scale_admin'):
            raise UserError(_('Solo un administrador de balanzas puede validar un perfil.'))
        if not self.evidence_attachment_id or not self.itegra_version or not self.format_version or not self.validation_note:
            raise UserError(_('Para validar, adjuntá un archivo aceptado por iTegra, informá sus versiones y documentá el resultado real.'))
        # No profile can claim compatibility until its serializer is implemented and tested.
        if self.adapter_code == 'kretz_itegra':
            raise UserError(_('El adaptador Kretz/iTegra está bloqueado: falta confirmar el formato y superar una importación real.'))
        super(ScaleExportProfile, self).write({
            'validation_state': 'validated',
            'validated_at': fields.Datetime.now(),
            'validated_by': self.env.user.id,
        })

    def action_reset_validation(self):
        if not self.env.user.has_group('pos_scale_management.group_scale_admin'):
            raise UserError(_('Solo un administrador de balanzas puede restablecer la validación.'))
        super(ScaleExportProfile, self).write({
            'validation_state': 'draft', 'validated_at': False,
            'validated_by': False,
        })
