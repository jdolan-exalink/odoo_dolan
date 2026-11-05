# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'DOLAN Advanced Views (Gantt, Cohort, Grid & Map)',
    'version': '20.0.1.2.0',
    'category': 'Hidden/Tools',
    'summary': 'Clean-room CE implementation of Gantt, Cohort, Weekly Grid and OpenStreetMap views for Odoo 20.0',
    'description': """
DOLAN Advanced Views for Odoo 20.0 CE
=====================================
Clean-room LGPL-3 implementation replacing proprietary Enterprise view types:
- web_gantt -> Full OWL 3 interactive timeline with dependency lines and drag bars.
- web_cohort -> Retention and recurrence cohort matrix visualization.
- web_grid -> Matrix hours and timesheet imputations by day/week.
- web_map -> Free OpenStreetMap Leaflet integration without proprietary Mapbox tokens.
    """,
    'author': 'DOLAN Open Source',
    'license': 'LGPL-3',
    'depends': ['web', 'base', 'project'],
    'data': [
        'security/ir.access.csv',
        'views/dolan_views_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'DOLAN_views/static/src/css/dolan_views.css',
            'DOLAN_views/static/src/xml/dolan_views.xml',
            'DOLAN_views/static/src/js/dolan_views.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
