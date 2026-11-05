# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Gestión de Alquileres (Rental)',
    'version': '20.0.1.1.0',
    'category': 'Sales/Rental',
    'summary': 'Alquiler de equipos por hora/día/semana/mes, reservas de serie, Pickup/Return y recargos por mora',
    'description': """
DOLAN Renting — Gestión Integral de Alquileres para Odoo 20 CE
==============================================================
Reemplazo clean-room 100% libre (LGPL-3) de:
- sale_renting
- sale_management_renting
- sale_stock_renting
- sale_mrp_renting
- sale_renting_crm
- sale_renting_project
- sale_renting_pdf_quote_builder
- pos_sale_stock_renting

Características principales:
- Configuración de productos alquilables (is_rental) con tarifas por Hora, Día, Semana y Mes.
- Configuración de penalidades automáticas por hora extra o día extra de demora.
- Integración nativa con sale.order (generación automática de orden de alquiler al confirmar).
- Órdenes de alquiler (dolan.rental.order) con control de disponibilidad, depósito en garantía y lotes/números de serie (stock.lot).
- Flujo operativo completo: Reserva -> Retiro (Pickup) -> Devolución (Return) -> Facturación (account.move).
- Vistas Calendar, Kanban, List y Form en el menú raíz Alquiler (secuencia 45).
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'stock',
        'account',
    ],
    'data': [
        'security/ir.access.csv',
        'data/rental_data.xml',
        'views/rental_views.xml',
        'views/sale_order_views.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'sequence': 45,
}
