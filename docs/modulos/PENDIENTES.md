# Pendientes

Actualizado el 13/11/2026. Lo que está en desarrollo sigue el orden que pidió Juan: Servicios (hecho),
Facturación y Finanzas (hecho: Cuentas corrientes y Caja y Tesorería), Inventario y Compras (hecho: Costos; el resto de la carpeta ya eran apps de Odoo), Gestión y Análisis (hecho). Comercial quedó en pausa.

## Apps del catálogo sin implementación propia

| Carpeta | App | Estado | Qué falta / decisión |
|---|---|---|---|
| Comercial | Fidelización | en pausa | Propuesta: activar `loyalty`, `sale_loyalty` y `pos_loyalty` de Odoo sin desarrollo propio y revisar que no choquen con `DOLAN_discount_engine`. Falta el OK. |
| Comercial | Tienda online | en pausa | `website_sale` de Odoo instala el sitio web completo. Queda como «Disponible para instalar» hasta decidir. |
| Logística | Preparación de pedidos, Rutas y reparto, Prueba de entrega | planificado | Sin empezar. |
| Configuraciones | Sucursales, Integraciones, Importaciones, Respaldos, Diagnóstico | en desarrollo / planificado | Sin empezar. |

## Pendientes dentro de los módulos ya hechos

Detalle en la sección *Pendiente* de cada documento:

* **Mesa de ayuda**: portal del cliente, tickets desde WhatsApp entrante, encuesta de satisfacción.
* **Agenda de turnos**: reserva por portal o link, seña con Mercado Pago, facturar el turno.
* **Órdenes de servicio**: app móvil sin conexión, descuento de stock de materiales, orden desde ticket o contrato.
* **Contratos**: descarga automática de índices BCRA/INDEC, PDF del contrato y firma digital, revisión legal.
* **Caja y Tesorería**: rendición automática del POS a la caja central, turno desde la pantalla del POS, entrega
  de caja entre cajeros, cajas por sucursal y en moneda extranjera.
* **Costos**: gastos de importación prorrateados con `stock_landed_costs`, reposición en dólares, aviso de
  aumentos de proveedor.
* **Flujo de caja**: suscripciones y contratos como entradas previstas, escenarios guardados, monedas extranjeras.
* **Rentabilidad**: margen por sucursal, costo con gastos de importación.
* **Auditoría**: motivo y aprobación en la interfaz, descuentos y devoluciones de POS y ventas, exportación firmada.
* **Alertas**: aviso por WhatsApp, resumen diario por correo.
* **Presupuesto financiero**: por centro de costo, alerta de cuenta excedida.
* **Cuentas corrientes**: cobranza activa por WhatsApp con reglas (horarios, exclusiones, opt-out, aprobación),
  bloqueo de venta con límite de crédito, multimoneda, filtro por sucursal.

## QA funcional (de todos los módulos beta)

Probar con datos reales en la base local antes de pasarlos a operativo. Ninguno se instaló todavía en 10.1.1.68
ni en 10.1.1.9: falta la aprobación escrita de Juan para conectarse por ssh.

## Otros pendientes del proyecto

* Perfiles del instalador: Completo no incluye Bancos, Cobranzas ni COT; Básico y Servicios no incluyen
  Promociones. Falta que Juan confirme si es a propósito.
* Tests Go del instalador: no se pueden correr en la PC de desarrollo (no hay Go); los corre la CI.
* Versiones desactualizadas en `installer/internal/packages/catalog.go` (ver `docs/audits/AUDITORIA_REPO.md`).
