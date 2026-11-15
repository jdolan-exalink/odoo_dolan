import os

from odoo import http
from odoo.http import request


class DolanBackupController(http.Controller):

    @http.route('/dolan_backup/download/<int:backup_id>', type='http', auth='user', methods=['GET'])
    def download(self, backup_id):
        if not request.env.user._is_system():
            return request.not_found()
        backup = request.env['dolan.backup'].browse(backup_id).exists()
        if not backup or not backup.path or not os.path.exists(backup.path):
            return request.not_found()
        stream = http.Stream(type='path', path=backup.path, mimetype='application/zip', as_attachment=True,
                             download_name=backup.name, size=os.path.getsize(backup.path), max_age=0)
        return stream.get_response()
