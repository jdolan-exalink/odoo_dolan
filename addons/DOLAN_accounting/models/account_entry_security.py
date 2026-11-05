"""Invoice operators use native payment services, never unrestricted journal entries.

The capability is a process-local identity, not a client-supplied boolean context flag.
No sudo is used: native access checks and company restrictions remain in force.
"""
from odoo import api, models
from odoo.exceptions import AccessError


_PAYMENT_CAPABILITY = object()
_CAPABILITY_KEY = '_dolan_native_payment_capability'


def _restricted(env):
    return not (
        env.su or env.context.get(_CAPABILITY_KEY) is _PAYMENT_CAPABILITY
        or env.user.has_group('account.group_account_user')
        or env.user.has_group('account.group_account_manager')
    )


def _deny(env):
    raise AccessError(env._('Los asientos manuales requieren permisos de Contabilidad. Utilice el registro de pagos para cobrar o pagar facturas.'))


def _guard(moves):
    if _restricted(moves.env) and any(move.move_type == 'entry' for move in moves):
        _deny(moves.env)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        if _restricted(self.env):
            default_type = self.env.context.get('default_move_type', 'entry')
            if any(vals.get('move_type', default_type) == 'entry' for vals in vals_list):
                _deny(self.env)
        return super().create(vals_list)

    def write(self, vals):
        _guard(self)
        if _restricted(self.env) and vals.get('move_type') == 'entry':
            _deny(self.env)
        return super().write(vals)

    def unlink(self):
        _guard(self)
        return super().unlink()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        move_ids = [vals.get('move_id') or self.env.context.get('default_move_id') for vals in vals_list]
        _guard(self.env['account.move'].browse([move_id for move_id in move_ids if move_id]))
        return super().create(vals_list)

    def write(self, vals):
        _guard(self.move_id)
        if vals.get('move_id'):
            _guard(self.env['account.move'].browse(vals['move_id']))
        return super().write(vals)

    def unlink(self):
        _guard(self.move_id)
        return super().unlink()


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _dolan_payment_scope(self):
        return self.with_context(**{_CAPABILITY_KEY: _PAYMENT_CAPABILITY})

    def _dolan_check_payment_values(self, vals):
        if not _restricted(self.env):
            return
        for name, value in vals.items():
            field = self._fields.get(name)
            related = field.related if field else None
            related = related.split('.') if isinstance(related, str) else related
            if (
                name in ('move_id', 'line_ids', 'write_off_line_vals', 'force_balance')
                or (related and related[0] == 'move_id')
            ):
                _deny(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._dolan_check_payment_values(vals)
        return super(AccountPayment, self._dolan_payment_scope()).create(vals_list)

    def write(self, vals):
        self._dolan_check_payment_values(vals)
        return super(AccountPayment, self._dolan_payment_scope()).write(vals)

    def unlink(self):
        return super(AccountPayment, self._dolan_payment_scope()).unlink()

    def action_post(self):
        return super(AccountPayment, self._dolan_payment_scope()).action_post()

    def action_cancel(self):
        return super(AccountPayment, self._dolan_payment_scope()).action_cancel()

    def action_draft(self):
        return super(AccountPayment, self._dolan_payment_scope()).action_draft()


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        # Private native service computes payment lines, write-offs and FX differences.
        scoped = self.with_context(**{_CAPABILITY_KEY: _PAYMENT_CAPABILITY})
        return super(AccountPaymentRegister, scoped)._create_payments()
