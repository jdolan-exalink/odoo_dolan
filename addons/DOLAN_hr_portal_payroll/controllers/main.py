# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.DOLAN_hr_portal.controllers.main import DolanPersonalPortal


class DolanPersonalPortalPayroll(DolanPersonalPortal):

    def _dolan_values(self, employee):
        values = super()._dolan_values(employee)
        values['slips'] = request.env['dolan.payroll.slip'].sudo().search([
            ('employee_id', '=', employee.id), ('state', '=', 'done')], order='date_to desc', limit=24)
        return values

    def _dolan_own_slip(self, slip_id):
        employee = self._dolan_employee()
        slip = request.env['dolan.payroll.slip'].sudo().browse(slip_id).exists()
        if not employee or not slip or slip.employee_id != employee or slip.state != 'done':
            raise request.not_found()
        return slip

    @http.route('/my/personal/slip/<int:slip_id>/pdf', type='http', auth='user', website=True)
    def dolan_personal_slip_pdf(self, slip_id, **kw):
        slip = self._dolan_own_slip(slip_id)
        pdf, _type = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'DOLAN_payroll_ar.action_report_payroll_receipt', slip.ids)
        filename = 'Recibo_%s.pdf' % slip.date_to.strftime('%Y%m')
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'), ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename="%s"' % filename)])

    @http.route('/my/personal/slip/<int:slip_id>/sign', type='http', auth='user', methods=['POST'], website=True)
    def dolan_personal_slip_sign(self, slip_id, disagreement=None, note=None, **kw):
        slip = self._dolan_own_slip(slip_id)
        try:
            # _check_can_sign compara el dueño del recibo con el usuario real (sudo no cambia el usuario).
            signer = slip
            if disagreement:
                signer._employee_sign('disagreement', (note or '').strip()[:2000] or _('Firmado en disconformidad.'))
            else:
                signer.action_employee_sign()
        except (UserError, AccessError) as exc:
            return self._dolan_back(error=str(exc), anchor='#slips')
        return self._dolan_back(message=_('Recibo firmado.'), anchor='#slips')
