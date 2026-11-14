# Módulos nuevos de la distribución DOLAN (PRD maestro v1.1)

Índice de los módulos creados a partir del PRD maestro, con su documentación y estado. Lo que falta está en
[PENDIENTES.md](PENDIENTES.md). El estado de cada app del Inicio se ve también en *Catálogo de apps*.

| Carpeta | App | Módulo | Estado | Documentación |
|---|---|---|---|---|
| Configuraciones | Catálogo de apps | `DOLAN_app_catalog` | operativo | [DOLAN_app_catalog.md](DOLAN_app_catalog.md) |
| Servicios | Mesa de ayuda | `DOLAN_helpdesk` | beta | [DOLAN_helpdesk.md](DOLAN_helpdesk.md) |
| Servicios | Agenda de turnos | `DOLAN_appointment` | beta | [DOLAN_appointment.md](DOLAN_appointment.md) |
| Servicios | Órdenes de servicio | `DOLAN_field_service` | beta | [DOLAN_field_service.md](DOLAN_field_service.md) |
| Servicios | Contratos | `DOLAN_service_contract` | beta | [DOLAN_service_contract.md](DOLAN_service_contract.md) |
| Facturación y Finanzas | Cuentas corrientes | `DOLAN_current_account` | beta | [DOLAN_current_account.md](DOLAN_current_account.md) |
| Facturación y Finanzas · Punto de venta y caja | Caja y Tesorería · Turnos de caja | `DOLAN_treasury` | beta | [DOLAN_treasury.md](DOLAN_treasury.md) |
| Inventario y Compras | Costos | `DOLAN_product_cost` | beta | [DOLAN_product_cost.md](DOLAN_product_cost.md) |
| Gestión y Análisis | Flujo de caja | `DOLAN_cash_flow` | beta | [DOLAN_cash_flow.md](DOLAN_cash_flow.md) |
| Gestión y Análisis | Rentabilidad | `DOLAN_profitability` | beta | [DOLAN_profitability.md](DOLAN_profitability.md) |
| Gestión y Análisis | Auditoría | `DOLAN_audit_log` | beta | [DOLAN_audit_log.md](DOLAN_audit_log.md) |
| Gestión y Análisis | Alertas | `DOLAN_alerts` | beta | [DOLAN_alerts.md](DOLAN_alerts.md) |
| Gestión y Análisis | Presupuesto financiero | `DOLAN_budget` | beta | [DOLAN_budget.md](DOLAN_budget.md) |

**Beta** quiere decir que el módulo está implementado y con pruebas automáticas, pero todavía no pasó QA
funcional con datos reales. Pasa a operativo cuando cumpla sus criterios de aceptación.

## Convenciones de todos los módulos nuevos

* Odoo 20 CE: permisos en `security/ir.access.csv` con dominio por empresa (`company_ids`), grupos con
  `res.groups.privilege`, sin `ir.rule`.
* Numeración propia por empresa con `ir.sequence` (TK-, TU-, OS-, CT-).
* Nada de saldos o datos fiscales paralelos: lo contable sale de los asientos y lo facturable va por el circuito
  normal de Facturación ARCA.
* WhatsApp siempre por DOLAN WhatsApp y, salvo los recordatorios que el usuario activa, revisado por una persona.
* Íconos: un dibujo propio por app, sin repetir, en Expresivo 3D, Flat, Mosaico, Mosaico de marca y Contorno;
  el color sale de la carpeta (ver `DOLAN_app_catalog.md`).
* Pruebas: `docker run ... odoo-bin -d <base descartable> -i <módulo> --test-tags /<módulo>`.
