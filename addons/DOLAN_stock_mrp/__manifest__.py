# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'DOLAN Barcode Scanner, Shop Floor MRP & Quality Control',
    'version': '20.0.1.1.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Clean-room CE Stock Barcode Terminal, MRP Shop Floor Workorder Terminal, Equipment Maintenance & Quality Control Suite',
    'description': """
DOLAN Supply Chain & Manufacturing Suite (Odoo 20.0 CE)
==============================================================================
Clean-room LGPL-3 implementation providing:
- Barcode Terminal (`stock_barcode` & `stock_barcode_mrp`): Scan EAN13, Code128, Lots and Locations for Receipts, Deliveries, Internal Transfers and Physical Inventory Adjustments with 1-click validation and OpenFoodFacts/UPC barcode lookup.
- Shop Floor / Taller (`mrp_workorder`, `mrp_workorder_hr_account`, `mrp_maintenance`): Touch terminal for workorders with Start/Pause/Done actions, operator assignment (`hr.employee`), hourly labor cost calculation, scrap registration and 1-click equipment maintenance request (`maintenance.request`).
- Quality Control (`quality`): Quality Control Points (`dolan.quality.point`), Quality Checks (`dolan.quality.check` with pass/fail, dimensional measurement with tolerances, and instructions), and Non-Conformance Quality Alerts (`dolan.quality.alert`).
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['stock', 'mrp', 'hr', 'maintenance', 'barcodes'],
    'data': [
        'security/ir.access.csv',
        'views/stock_mrp_quality_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
