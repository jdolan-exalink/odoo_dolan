import re
from urllib.parse import quote

from odoo import http
from odoo.http import request

REF_RE = re.compile(r'^[a-z0-9_:/-]{1,120}$')


class DolanHelpController(http.Controller):
    """Links cortos para mandar por WhatsApp o correo: /ayuda/facturacion/emitir-factura."""

    @http.route(['/ayuda', '/ayuda/<path:ref>'], type='http', auth='user', methods=['GET'])
    def help_link(self, ref=None, **_kwargs):
        url = '/odoo/ayuda'
        if ref and REF_RE.match(ref):
            url += '?ref=' + quote(ref, safe=':/')
        return request.redirect(url, local=True)
