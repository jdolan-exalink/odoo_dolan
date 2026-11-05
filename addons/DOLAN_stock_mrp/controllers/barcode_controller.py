# Part of Odoo. See LICENSE file for full copyright and licensing details.

import html
from odoo import http
from odoo.http import request


class DolanBarcodeTerminalController(http.Controller):

    @http.route('/dolan_stock_mrp/barcode_terminal', type='http', auth='user', website=False, methods=['GET', 'POST'])
    def barcode_scanner_terminal(self, session_id=None, barcode=None, picking_id=None, **kwargs):
        """Interactive touch & USB/Bluetooth scanner terminal for Stock Barcode & Physical Inventory."""
        Session = request.env['dolan.stock.barcode.session'].sudo()
        if session_id:
            session = Session.browse(int(session_id))
        else:
            session = Session.search([('state', '=', 'in_progress')], limit=1)
            if not session:
                session = Session.create({'operation_mode': 'picking'})

        if picking_id and str(picking_id).isdigit():
            session.picking_id = int(picking_id)

        if request.httprequest.method == 'POST' and barcode:
            session.barcode_input = barcode
            try:
                session.action_process_barcode()
            except Exception as exc:
                session.last_scan_status = 'error'
                session.last_scan_message = str(exc)

        pickings = request.env['stock.picking'].sudo().search(
            [('state', 'not in', ('done', 'cancel'))], limit=25
        )
        picking_options = ''.join(
            f"<option value='{p.id}' {'selected' if session.picking_id.id == p.id else ''}>"
            f"{html.escape(p.name)} ({html.escape(p.picking_type_id.name or '')})</option>"
            for p in pickings
        )

        lines_rows = ''.join(
            f"<tr>"
            f"<td><code>{html.escape(l.barcode or '')}</code></td>"
            f"<td><strong>{html.escape(l.product_id.display_name or '')}</strong></td>"
            f"<td>{html.escape(l.location_id.complete_name or '-')}</td>"
            f"<td style='text-align:right;font-weight:800;font-size:1.15rem;'>{l.scanned_qty:g}</td>"
            f"</tr>"
            for l in session.line_ids
        )

        status_bg = {
            'ok': '#d1e7dd',
            'warning': '#fff3cd',
            'error': '#f8d7da',
        }.get(session.last_scan_status or 'ok', '#d1e7dd')

        body = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8"/>
    <title>DOLAN Barcode Scanner Terminal</title>
</head>
<body style="margin:0;font-family:system-ui,-apple-system,sans-serif;background:#f1f3f5;color:#212529;">
    <header style="background:#212529;color:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h2 style="margin:0;">📦 DOLAN Terminal de Código de Barras ({html.escape(session.name)})</h2>
            <small style="color:#adb5bd;">Escanee EAN13 / Code128 / Ubicaciones / Remitos</small>
        </div>
        <a href="/odoo" style="color:#fff;background:#495057;padding:8px 16px;border-radius:6px;text-decoration:none;">Volver a Odoo</a>
    </header>
    <main style="max-width:960px;margin:24px auto;background:#fff;padding:24px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,0.08);">
        <form method="POST" action="/dolan_stock_mrp/barcode_terminal" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px;">
            <input type="hidden" name="csrf_token" value="{request.csrf_token()}"/>
            <input type="hidden" name="session_id" value="{session.id}"/>
            <select name="picking_id" style="padding:12px;border-radius:8px;border:1px solid #ced4da;font-size:1rem;min-width:260px;">
                <option value="">-- Seleccionar Remito Activo --</option>
                {picking_options}
            </select>
            <input type="text" name="barcode" autofocus="autofocus"
                   placeholder="Escanee código EAN13, Ubicación o Remito..."
                   style="flex:1;padding:12px 16px;font-size:1.2rem;border:2px solid #0d6efd;border-radius:8px;"/>
            <button type="submit" style="background:#0d6efd;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:1.1rem;font-weight:700;cursor:pointer;">
                Procesar Escaneo
            </button>
        </form>
        {f'<div style="background:{status_bg};padding:12px 16px;border-radius:8px;margin-bottom:18px;font-weight:600;">{html.escape(session.last_scan_message)}</div>' if session.last_scan_message else ''}
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f8f9fa;border-bottom:2px solid #dee2e6;text-align:left;">
                    <th style="padding:10px;">Código</th>
                    <th style="padding:10px;">Producto</th>
                    <th style="padding:10px;">Ubicación</th>
                    <th style="padding:10px;text-align:right;">Cantidad Escaneada</th>
                </tr>
            </thead>
            <tbody>
                {lines_rows or '<tr><td colspan="4" style="padding:20px;text-align:center;color:#6c757d;">Aún no se han escaneado productos en esta sesión.</td></tr>'}
            </tbody>
        </table>
    </main>
</body>
</html>"""
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')])
