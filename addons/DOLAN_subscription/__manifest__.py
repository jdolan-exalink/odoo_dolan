# -*- coding: utf-8 -*-
# Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
{
    'name': 'DOLAN - Suscripciones y Facturación Recurrente',
    'version': '20.0.1.1.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Contratos recurrentes, planes periódicos, facturación automática ARCA y métricas MRR/ARR/Churn',
    'description': """
DOLAN Subscription — Gestión de Suscripciones e Ingresos Recurrentes (Odoo 20 CE)
=================================================================================
Reemplazo clean-room 100% libre (LGPL-3) de:
- sale_subscription
- sale_subscription_stock
- crm_sale_subscription
- project_sale_subscription
- pos_sale_subscription

Características principales:
- Planes de recurrencia: Mensual, Bimestral, Trimestral, Semestral y Anual.
- Cálculo automático en tiempo real de MRR (Monthly Recurring Revenue) y ARR (Annual Recurring Revenue).
- Generación manual y por tarea programada (ir.cron) de facturas recurrentes en account.move.
- Integración nativa con sale.order (generación automática al confirmar pedido recurrente).
- Envío automático de factura por correo electrónico y vínculo con CRM (crm.lead) y Proyectos (project.project).
- Gestión de estados (Borrador, Activa, Pausada, Cerrada) y motivos de baja (Churn analysis).
- Vistas Kanban, List, Form, Pivot y Graph de MRR/ARR.
    """,
    'author': 'DOLAN Open Source Argentina',
    'website': 'https://github.com/dolan-ce/odoo20-rea',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'account',
        'crm',
        'project',
    ],
    'data': [
        'security/ir.access.csv',
        'data/subscription_cron.xml',
        'views/sale_subscription_views.xml',
        'views/sale_order_views.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'sequence': 40,
}
