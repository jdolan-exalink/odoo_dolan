# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
from odoo import http
from odoo.http import request, Response


class DolanPwaController(http.Controller):

    @http.route('/dolan_theme/manifest.json', type='http', auth='public', methods=['GET'], csrf=False)
    def manifest(self):
        """Devuelve el Web App Manifest estándar para instalación PWA."""
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        manifest_data = {
            "name": "DOLAN ERP - Gestión Empresarial",
            "short_name": "DOLAN",
            "description": "Sistema de Gestión Empresarial y Facturación Argentina para DOLAN",
            "start_url": "/odoo",
            "scope": "/",
            "display": "standalone",
            "orientation": "any",
            "background_color": "#F8FAFC",
            "theme_color": "#714B67",
            "icons": [
                {
                    "src": "/DOLAN_theme/static/description/icon.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable"
                },
                {
                    "src": "/DOLAN_theme/static/description/icon.svg",
                    "sizes": "512x512",
                    "type": "image/svg+xml",
                    "purpose": "any maskable"
                }
            ],
            "categories": ["business", "finance", "productivity"],
            "shortcuts": [
                {
                    "name": "Nueva Venta",
                    "url": "/odoo/action-sale.action_quotations_with_onboarding?menu_id=sale.sale_menu_root",
                    "description": "Crear un nuevo presupuesto de venta"
                },
                {
                    "name": "Facturas",
                    "url": "/odoo/action-account.action_move_out_invoice_type?menu_id=account.menu_finance",
                    "description": "Consultar facturas de clientes"
                },
                {
                    "name": "Contactos",
                    "url": "/odoo/action-contacts.action_contacts?menu_id=contacts.menu_contacts",
                    "description": "Directorio de clientes y proveedores"
                }
            ]
        }
        return Response(
            json.dumps(manifest_data, indent=2),
            content_type='application/manifest+json; charset=utf-8',
            headers=[
                ('Cache-Control', 'public, max-age=3600'),
                ('Access-Control-Allow-Origin', '*'),
            ]
        )

    @http.route('/dolan_theme/sw.js', type='http', auth='public', methods=['GET'], csrf=False)
    def service_worker(self):
        """Service Worker para cache de assets estáticos y funcionamiento PWA fluido."""
        sw_code = """// DOLAN ERP - Service Worker v1.1
const CACHE_NAME = 'dolan-pwa-v2';
const ASSETS_TO_CACHE = [
  '/DOLAN_theme/static/description/icon.svg',
  '/DOLAN_theme/static/description/icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Solo cachear recursos estáticos GET (CSS, JS, imágenes, fuentes)
  const url = new URL(event.request.url);
  if (
    event.request.method === 'GET' &&
    (url.pathname.includes('/static/') || url.pathname.includes('/web/assets/'))
  ) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          // Revalidación en segundo plano (stale-while-revalidate)
          fetch(event.request)
            .then((networkResponse) => {
              if (networkResponse && networkResponse.status === 200) {
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse));
              }
            })
            .catch(() => {});
          return cachedResponse;
        }
        return fetch(event.request);
      })
    );
  }
});
"""
        return Response(
            sw_code,
            content_type='application/javascript; charset=utf-8',
            headers=[
                ('Service-Worker-Allowed', '/'),
                ('Cache-Control', 'no-cache'),
            ]
        )
