import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    dolan_delivery_whatsapp = fields.Boolean('Avisar las entregas por WhatsApp',
                                             help='Valor inicial de la opción en cada hoja de ruta nueva.')


class DolanDeliveryRoute(models.Model):
    _inherit = 'dolan.delivery.route'

    notify_whatsapp = fields.Boolean('Avisar por WhatsApp al entregar',
                                     default=lambda self: self.env.company.dolan_delivery_whatsapp)


class DolanDeliveryStop(models.Model):
    _inherit = 'dolan.delivery.stop'

    whatsapp_state = fields.Selection([('sent', 'Avisado'), ('error', 'No se pudo avisar'), ('skipped', 'Sin aviso')],
                                      'Aviso por WhatsApp', readonly=True, copy=False)
    whatsapp_error = fields.Char('Error del aviso', readonly=True, copy=False)

    def _whatsapp_account(self):
        self.ensure_one()
        return self.env['dolan.whatsapp.account'].sudo().search([('company_id', '=', self.company_id.id)], limit=1)

    def _whatsapp_body(self):
        self.ensure_one()
        partial = self.state == 'partial'
        body = _('Hola %(name)s, %(what)s tu pedido %(ref)s.') % {
            'name': self.partner_id.name or '',
            'what': _('entregamos parte de') if partial else _('entregamos'),
            'ref': self.picking_id.origin or self.picking_id.name,
        }
        if self.received_by:
            body += ' ' + _('Recibió: %s.') % self.received_by
        if partial:
            body += ' ' + _('Lo que falta te lo llevamos en otra entrega.')
        return body + ' ' + _('Gracias, %s.') % self.company_id.name

    def _notify_whatsapp(self):
        for stop in self:
            if not stop.route_id.notify_whatsapp:
                continue
            account = stop._whatsapp_account()
            if not account or not stop.partner_id:
                stop.write({'whatsapp_state': 'skipped',
                            'whatsapp_error': _('No hay cuenta de WhatsApp de la empresa.') if not account else False})
                continue
            try:
                with self.env.cr.savepoint():
                    account.send_partner_text(stop.partner_id, stop._whatsapp_body())
                stop.write({'whatsapp_state': 'sent', 'whatsapp_error': False})
            except Exception as error:  # noqa: BLE001 - la entrega se registra aunque falle el aviso
                _logger.info('Aviso de entrega por WhatsApp falló en %s: %s', stop.picking_id.name, error)
                stop.write({'whatsapp_state': 'error', 'whatsapp_error': str(error)[:250]})

    def action_deliver(self):
        result = super().action_deliver()
        self._notify_whatsapp()
        return result

    def action_deliver_partial(self):
        result = super().action_deliver_partial()
        self._notify_whatsapp()
        return result
