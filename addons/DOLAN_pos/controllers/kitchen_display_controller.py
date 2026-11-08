# Part of Odoo. See LICENSE file for full copyright and licensing details.

import html
from odoo import http
from odoo.http import request


class DolanKitchenDisplayController(http.Controller):

    _station_labels = {
        'all': 'Todas las estaciones',
        'kitchen': 'Cocina',
        'bar': 'Barra',
        'coffee': 'Cafetería',
        'dessert': 'Postres',
    }
    _state_labels = {
        'pending': 'Pendiente',
        'preparing': 'En preparación',
        'ready': 'Listo',
        'delivered': 'Entregado',
    }

    @http.route('/dolan_pos/kitchen_display', type='http', auth='user', website=False)
    def kitchen_display_screen(self, station='all', **kwargs):
        """Interactive touch-friendly Kitchen Display Screen (KDS) with auto-refresh."""
        Ticket = request.env['dolan.pos.kitchen.ticket'].sudo()
        domain = [('state', 'in', ['pending', 'preparing', 'ready'])]
        if station and station != 'all':
            domain.append(('station', '=', station))

        tickets = Ticket.search(domain, order='priority desc, create_date asc')

        cards_html = []
        for t in tickets:
            badge_color = {
                'pending': '#ffc107',
                'preparing': '#0d6efd',
                'ready': '#198754',
            }.get(t.state, '#6c757d')
            border_style = '3px solid #dc3545' if t.is_delayed else f'2px solid {badge_color}'
            lines_html = ''.join(
                f"<li style='padding:6px 0;border-bottom:1px dashed #dee2e6;font-size:1.05rem;'>"
                f"<strong>{line.qty:g}x</strong> {html.escape(line.product_id.display_name or '')}"
                f"{(' <span style=\"color:#d63384;font-style:italic;\">(' + html.escape(line.note) + ')</span>') if line.note else ''}"
                f"</li>"
                for line in t.line_ids
            )
            delay_badge = (
                "<span style='background:#dc3545;color:#fff;padding:3px 8px;border-radius:4px;font-weight:bold;'>¡DEMORADO!</span>"
                if t.is_delayed else ""
            )
            cards_html.append(f"""
                <div style="background:#fff;border:{border_style};border-radius:10px;padding:14px;width:320px;box-shadow:0 3px 10px rgba(0,0,0,0.08);display:flex;flex-direction:column;justify-content:space-between;">
                    <div>
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                            <span style="font-size:1.25rem;font-weight:800;">#{html.escape(t.name or '')}</span>
                            <span style="background:{badge_color};color:#fff;padding:4px 10px;border-radius:6px;font-weight:700;">
                                {html.escape(self._state_labels.get(t.state, t.state))}
                            </span>
                        </div>
                        <div style="font-size:0.9rem;color:#495057;margin-bottom:8px;">
                            <strong>Mesa:</strong> {html.escape(t.table_name or 'Mostrador')} |
                            <strong>Estación:</strong> {html.escape(self._station_labels.get(t.station, t.station))} |
                            <strong>⏱ {t.elapsed_minutes} min</strong> {delay_badge}
                        </div>
                        <ul style="list-style:none;padding:0;margin:0 0 12px 0;">
                            {lines_html}
                        </ul>
                    </div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;">
                        <a href="/dolan_pos/kitchen_ticket/action/{t.id}/start?station={html.escape(station)}"
                           style="flex:1;text-align:center;background:#0d6efd;color:#fff;text-decoration:none;padding:10px;border-radius:6px;font-weight:700;">
                           Preparar
                        </a>
                        <a href="/dolan_pos/kitchen_ticket/action/{t.id}/ready?station={html.escape(station)}"
                           style="flex:1;text-align:center;background:#198754;color:#fff;text-decoration:none;padding:10px;border-radius:6px;font-weight:700;">
                           ¡Listo!
                        </a>
                        <a href="/dolan_pos/kitchen_ticket/action/{t.id}/delivered?station={html.escape(station)}"
                           style="flex:1;text-align:center;background:#212529;color:#fff;text-decoration:none;padding:10px;border-radius:6px;font-weight:700;">
                           Entregar
                        </a>
                    </div>
                </div>
            """)

        body = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8"/>
    <meta http-equiv="refresh" content="10"/>
    <title>Pantalla de cocina · DOLAN</title>
</head>
<body style="margin:0;font-family:system-ui,-apple-system,sans-serif;background:#1e2229;color:#212529;">
    <header style="background:#111418;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h2 style="margin:0;">🍳 Pantalla de preparación · DOLAN</h2>
            <small style="color:#adb5bd;">Auto-refresco cada 10s · Pantalla Táctil de Cocina, Barra y Cafetería</small>
        </div>
        <div style="display:flex;gap:8px;">
            <a href="/dolan_pos/kitchen_display?station=all" style="color:#fff;background:#495057;padding:8px 14px;border-radius:6px;text-decoration:none;">Todas</a>
            <a href="/dolan_pos/kitchen_display?station=kitchen" style="color:#fff;background:#0d6efd;padding:8px 14px;border-radius:6px;text-decoration:none;">Cocina</a>
            <a href="/dolan_pos/kitchen_display?station=bar" style="color:#fff;background:#6610f2;padding:8px 14px;border-radius:6px;text-decoration:none;">Barra</a>
            <a href="/dolan_pos/kitchen_display?station=coffee" style="color:#fff;background:#fd7e14;padding:8px 14px;border-radius:6px;text-decoration:none;">Cafetería</a>
            <a href="/dolan_pos/kitchen_display?station=dessert" style="color:#fff;background:#d63384;padding:8px 14px;border-radius:6px;text-decoration:none;">Postres</a>
            <a href="/dolan_pos/order_tracking" target="_blank" style="color:#fff;background:#198754;padding:8px 14px;border-radius:6px;text-decoration:none;">Pantalla Clientes</a>
        </div>
    </header>
    <main style="padding:20px;display:flex;flex-wrap:wrap;gap:16px;">
        {''.join(cards_html) if cards_html else '<div style="color:#fff;font-size:1.3rem;padding:40px;">No hay comandas pendientes en esta estación.</div>'}
    </main>
</body>
</html>"""
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/dolan_pos/kitchen_ticket/action/<int:ticket_id>/<string:op>', type='http', auth='user', website=False)
    def kitchen_ticket_state_action(self, ticket_id, op, station='all', **kwargs):
        ticket = request.env['dolan.pos.kitchen.ticket'].sudo().browse(ticket_id)
        if ticket.exists():
            if op == 'start':
                ticket.action_start_preparing()
            elif op == 'ready':
                ticket.action_mark_ready()
            elif op == 'delivered':
                ticket.action_mark_delivered()
        return request.redirect(f'/dolan_pos/kitchen_display?station={station}')

    @http.route('/dolan_pos/order_tracking', type='http', auth='public', website=False)
    def customer_order_tracking_screen(self, **kwargs):
        """Public customer-facing display showing orders in preparation vs ready for pickup."""
        Ticket = request.env['dolan.pos.kitchen.ticket'].sudo()
        preparing_tickets = Ticket.search([('state', 'in', ['pending', 'preparing'])], limit=30)
        ready_tickets = Ticket.search([('state', '=', 'ready')], limit=30)

        prep_badges = ''.join(
            f"<div style='background:#343a40;color:#ffc107;font-size:2rem;font-weight:800;padding:16px 26px;border-radius:10px;'>"
            f"#{html.escape(t.pos_reference or t.name)}</div>"
            for t in preparing_tickets
        )
        ready_badges = ''.join(
            f"<div style='background:#198754;color:#fff;font-size:2.4rem;font-weight:900;padding:18px 30px;border-radius:12px;box-shadow:0 4px 12px rgba(25,135,84,0.45);'>"
            f"#{html.escape(t.pos_reference or t.name)}</div>"
            for t in ready_tickets
        )

        body = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8"/>
    <meta http-equiv="refresh" content="8"/>
    <title>Estado de su pedido · DOLAN</title>
</head>
<body style="margin:0;font-family:system-ui,-apple-system,sans-serif;background:#121519;color:#fff;height:100vh;display:flex;flex-direction:column;">
    <div style="display:flex;flex:1;">
        <section style="flex:1;padding:30px;border-right:2px solid #2b3035;">
            <h1 style="color:#ffc107;font-size:2.2rem;margin-top:0;">⏳ EN PREPARACIÓN</h1>
            <div style="display:flex;flex-wrap:wrap;gap:16px;">
                {prep_badges or '<p style="color:#6c757d;font-size:1.3rem;">Sin pedidos en preparación</p>'}
            </div>
        </section>
        <section style="flex:1;padding:30px;background:#16241c;">
            <h1 style="color:#20c997;font-size:2.2rem;margin-top:0;">✅ LISTO PARA RETIRAR</h1>
            <div style="display:flex;flex-wrap:wrap;gap:16px;">
                {ready_badges or '<p style="color:#adb5bd;font-size:1.3rem;">Aguardando próximos pedidos listos...</p>'}
            </div>
        </section>
    </div>
</body>
</html>"""
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')])
