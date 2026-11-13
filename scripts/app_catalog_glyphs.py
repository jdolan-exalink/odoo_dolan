"""Glifos propios (24x24, trazo) para las apps del catálogo DOLAN.

Dibujados para este repositorio (licencia LGPL-3 del proyecto), con el estilo
de trazo redondeado de Tabler para convivir con el resto del set. Cada glifo es
SVG interno a un <g> con stroke; build_app_catalog.py lo convierte a las cinco
familias del theme (fluent_3d, fluent_flat, fluent_filled, fluent_regular, tabler).
"""

GLYPHS = {
    # Comercial
    "quotations": '<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/><path d="M8.5 9h2"/>',
    "customers": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1"/><path d="M16 4.2a3.5 3.5 0 0 1 0 6.6M18 14.2a5 5 0 0 1 3 4.8v1"/>',
    "pricelists": '<path d="M4 4h7l9 9-7 7-9-9V4Z"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M11.5 14.5l3-3"/>',
    "marketplace": '<path d="M4 9l1.5-5h13L20 9"/><path d="M4 9a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0A2.7 2.7 0 0 0 20 9"/><path d="M5 11.5V20h14v-8.5"/><path d="M10 20v-4h4v4"/>',
    "ecommerce": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/><path d="M8 8.5h1.2l1.3 4.5h4.8l1-3.2H10"/>',
    "loyalty": '<path d="M12 4l2.3 4.7 5.2.8-3.8 3.6.9 5.1L12 15.8 7.4 18.2l.9-5.1L4.5 9.5l5.2-.8L12 4Z"/>',
    # Finanzas
    "current_accounts": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/><path d="M15.5 15v3M14 16.5h3"/>',
    "debtors": '<circle cx="10" cy="8" r="3.5"/><path d="M4 20v-1a5 5 0 0 1 5-5h2"/><circle cx="17.5" cy="17" r="3.5"/><path d="M17.5 15.5v1.8l1 .7"/>',
    "collections": '<path d="M3 15h4l3 2h5a1.5 1.5 0 0 0 0-3h-3"/><path d="M7 15v4H3v-4"/><path d="M11 14l6.3-2.3a1.6 1.6 0 0 1 1.2 3L13 18"/><circle cx="15" cy="6" r="3"/>',
    "vendor_payments": '<rect x="3" y="7" width="15" height="11" rx="2"/><path d="M18 4l3 3-3 3M21 7h-6"/><circle cx="10.5" cy="12.5" r="2.3"/><path d="M6 10.5v4"/>',
    "treasury": '<path d="M4 10h16v10H4z"/><path d="M3 10l9-6 9 6"/><path d="M8 13v4M12 13v4M16 13v4"/>',
    "banks": '<path d="M3 9l9-5 9 5"/><path d="M4 20h16M5 9v8M9.5 9v8M14.5 9v8M19 9v8M4 17h16"/>',
    "checks": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 14.5c1-1.5 2-1.5 3 0s2 1.5 3 0M15 14h3M6 9.5h5"/><path d="M15 10h3"/>',
    "reconciliation": '<path d="M4 7h11M12 4l3 3-3 3"/><path d="M20 17H9M12 14l-3 3 3 3"/>',
    "taxes": '<circle cx="12" cy="12" r="9"/><path d="M9 15l6-6"/><circle cx="9.3" cy="9.3" r="1"/><circle cx="14.7" cy="14.7" r="1"/>',
    "fiscal_reports": '<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5"/><path d="M9 17v-3M12 17v-6M15 17v-2"/>',
    "financial_reports": '<path d="M4 20h16"/><rect x="5" y="11" width="3" height="6" rx=".8"/><rect x="10.5" y="7" width="3" height="10" rx=".8"/><rect x="16" y="4" width="3" height="13" rx=".8"/>',
    # Punto de venta
    "pos_closing": '<rect x="3" y="10" width="18" height="10" rx="2"/><path d="M6 10V5h8v5"/><path d="M8 7.5h4"/><path d="M8.5 15l2 2 4-4"/>',
    "cash_shifts": '<rect x="3" y="9" width="13" height="11" rx="2"/><path d="M6 9V5h7v4"/><circle cx="17.5" cy="7.5" r="4"/><path d="M17.5 5.8v1.9l1.2.8"/><path d="M7 14.5h5"/>',
    # Inventario y compras
    "products": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/><path d="M8 5.3l8 4.5"/>',
    "suppliers": '<path d="M3 20V9l6-4v4l6-4v4l6-4v15H3Z"/><path d="M7 16h2M12 16h2M17 16h1"/>',
    "replenishment": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4.5h-4.5"/><path d="M9 12.5l2 2 4-4"/>',
    "transfers": '<rect x="2.5" y="8" width="7" height="7" rx="1.2"/><rect x="14.5" y="8" width="7" height="7" rx="1.2"/><path d="M9.5 10h5M12.5 8l2 2-2 2"/><path d="M14.5 13.5h-5"/>',
    "lots": '<path d="M4 6h3M4 10h3M4 14h3M4 18h3"/><path d="M10 6v12M13 6v12M16 6v12M19 6v12"/>',
    "stock_count": '<rect x="4" y="4" width="16" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M8 11l1.5 1.5L12 10M8 16.5l1.5 1.5L12 15.5M14 11.5h2.5M14 17h2.5"/>',
    "costs": '<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2A2.5 2.5 0 0 0 12.5 8h-1a2 2 0 0 0 0 4h1a2 2 0 0 1 0 4h-1a2.5 2.5 0 0 1-2.3-1.2M12 6.5V8M12 16v1.5"/>',
    # Logística
    "delivery_notes": '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/><path d="M9 11h7M9 14h7M9 17h4"/>',
    "picking": '<path d="M4 7l8-4 8 4-8 4-8-4Z"/><path d="M4 7v9l8 4 8-4V7"/><path d="M8.5 13.5l2 2 4-4"/>',
    "routes": '<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H16a3 3 0 0 0 0-6H8a3 3 0 0 1 0-6h7.5"/>',
    "proof_delivery": '<path d="M3 7l9-4 9 4v10l-9 4-9-4V7Z"/><path d="M3 7l9 4 9-4M12 11v10"/><path d="M15 15.5l1.5 1.5 3-3"/>',
    # Personal
    "hr_novelties": '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/><path d="M12 13v5M9.5 15.5h5"/>',
    "hr_documents": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><circle cx="12" cy="12.5" r="2"/><path d="M8.5 17.5a3.5 3.5 0 0 1 7 0"/>',
    # Industria
    "quality": '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z"/><path d="M9 12l2 2 4-4"/>',
    "assets": '<path d="M4 20V10l8-6 8 6v10"/><path d="M4 20h16"/><path d="M9.5 20v-6h5v6"/><path d="M15.5 9.5h.01"/>',
    # Servicios
    "contracts": '<path d="M14 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9l4 4v4"/><path d="M8 8h6M8 11.5h4"/><path d="M7.5 16.5c1-1.6 1.8-1.6 2.4 0 .5 1.1 1.1 1.1 1.8-.3"/><circle cx="18" cy="15.5" r="2.8"/><path d="M16.8 18l-.8 3.5 2-1 2 1-.8-3.5"/>',
    "appointments": '<path d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7z"/><path d="M4.5 7.5h4M4.5 12h4M4.5 16.5h4"/><path d="M11.5 12l2 2 3.5-3.5"/>',
    "helpdesk": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M14.9 14.9l3.5 3.5M9.1 14.9l-3.5 3.5M5.6 5.6l3.5 3.5M18.4 5.6l-3.5 3.5"/>',
    "service_orders": '<path d="M12 21.5s-7-6-7-12a7 7 0 0 1 14 0c0 6-7 12-7 12Z"/><path d="M10.2 11.8l3.3-3.3"/><path d="M14.6 6.6a1.6 1.6 0 1 0 .8 2.7l-1.9-.8Z"/><path d="M9.4 12.6a.9.9 0 1 0 0 0Z"/>',
    # Comunicación e IA
    "ocr": '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M8 9h8M8 12h8M8 15h5"/>',
    "templates": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5l8.5 6 8.5-6"/><path d="M14 19v-4h5"/>',
    "automations": '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6L13 3Z"/>',
    # Gestión
    "executive_dashboard": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/><path d="M7 17v-3M11 17v-5M15 17v-2"/><circle cx="17.5" cy="13" r="1.5"/>',
    "profitability": '<path d="M3 17l5.5-5.5 3.5 3.5 7-7"/><path d="M14 8h5v5"/><path d="M3 21h18"/>',
    "cash_flow": '<path d="M4 16c3 0 3-8 6-8s3 8 6 8 3-6 4-6"/><path d="M3 20h18"/><path d="M5 4v4M3 6h4"/>',
    "audit": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/><path d="M8 10.5l1.8 1.8L13.5 8.5"/>',
    "alerts": '<path d="M10 5a2 2 0 1 1 4 0 7 7 0 0 1 4 6v3l2 3H4l2-3v-3a7 7 0 0 1 4-6"/><path d="M9.5 17a2.5 2.5 0 0 0 5 0"/>',
    "budget": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l6.5 6.2"/><path d="M12 12H3.5"/>',
    # Configuración
    "companies": '<rect x="4" y="3" width="10" height="18" rx="1.5"/><path d="M14 9h5a1.5 1.5 0 0 1 1.5 1.5V21H14"/><path d="M7.5 7h3M7.5 11h3M7.5 15h3M17 13h1M17 17h1"/>',
    "branches": '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="19" r="2.5"/><circle cx="19" cy="19" r="2.5"/><path d="M12 7.5v4.5M12 12l-6 4.7M12 12l6 4.7"/>',
    "users": '<circle cx="12" cy="8" r="4"/><path d="M5 21v-1.5A5.5 5.5 0 0 1 10.5 14h3a5.5 5.5 0 0 1 5.5 5.5V21"/><path d="M16.5 4.5l1.5-1.5M7.5 4.5L6 3"/>',
    "fiscal_settings": '<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5"/><circle cx="12" cy="14.5" r="2.5"/><path d="M12 10.5v1.5M12 17v1.5M8 14.5h1.5M14.5 14.5H16"/>',
    "integrations": '<path d="M9 7V3M15 7V3"/><path d="M6 7h12v4a6 6 0 0 1-12 0V7Z"/><path d="M12 17v4"/>',
    "imports": '<path d="M12 3v11M8 10l4 4 4-4"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "app_catalog": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><path d="M17 13.5v7M13.5 17h7"/>',
    "backups": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3M19 6v4"/><path d="M5 12v6c0 1.7 3.1 3 7 3"/><path d="M17.5 13v6M15 16.5l2.5 2.5 2.5-2.5"/>',
    "diagnostics": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
}
