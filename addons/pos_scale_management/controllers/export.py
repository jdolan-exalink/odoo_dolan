from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.http.stream import content_disposition


class ScaleExportController(http.Controller):

    @http.route(
        '/pos_scale_management/export/<int:job_id>/download',
        type='http', auth='user', methods=['GET'], csrf=False,
    )
    def download_export(self, job_id, **kwargs):
        job = request.env['scale.export.job'].browse(job_id).exists()
        if not job:
            return request.not_found()
        try:
            job.check_access('read')
        except AccessError:
            return request.not_found()
        if not any(request.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
            'pos_scale_management.group_scale_operator',
        )):
            return request.not_found()
        if not job.file_data or job.state not in ('generated', 'downloaded', 'pending_import', 'imported_reported', 'import_failed_reported'):
            raise UserError(_('Esta exportación no contiene un archivo descargable.'))
        job._mark_downloaded()
        content = job.file_data.content
        return request.make_response(content, headers=[
            ('Content-Type', 'application/octet-stream'),
            ('Content-Length', str(len(content))),
            ('Content-Disposition', content_disposition(job.file_name or 'balanza.dat')),
            ('Cache-Control', 'no-store'),
        ])
