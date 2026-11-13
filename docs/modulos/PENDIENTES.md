# Pendientes

Actualizado el 13/11/2026. Lo que está en desarrollo sigue el orden que pidió Juan: Servicios (hecho),
Facturación y Finanzas (en curso), Inventario y Compras. Comercial quedó en pausa.

## Apps del catálogo sin implementación propia

| Carpeta | App | Estado | Qué falta / decisión |
|---|---|---|---|
| Comercial | Fidelización | en pausa | Propuesta: activar `loyalty`, `sale_loyalty` y `pos_loyalty` de Odoo sin desarrollo propio y revisar que no choquen con `DOLAN_discount_engine`. Falta el OK. |
| Comercial | Tienda online | en pausa | `website_sale` de Odoo instala el sitio web completo. Queda como «Disponible para instalar» hasta decidir. |
| Facturación y Finanzas | Caja y Tesorería | en desarrollo | Cajas, apertura y cierre, arqueo por denominación, movimientos, transferencias, rendiciones. |
| Punto de venta | Turnos de caja | en desarrollo | Va junto con Caja y Tesorería. |
| Inventario y Compras | Costos | planificado | Próximo después de Finanzas. |
| Logística | Preparación de pedidos, Rutas y reparto, Prueba de entrega | planificado | Sin empezar. |
| Gestión y Análisis | Rentabilidad, Flujo de caja, Auditoría, Alertas, Presupuesto financiero | en desarrollo / planificado | Sin empezar. |
| Configuraciones | Sucursales, Integraciones, Importaciones, Respaldos, Diagnóstico | en desarrollo / planificado | Sin empezar. |

## Pendientes dentro de los módulos ya hechos

Detalle en la sección *Pendiente* de cada documento:

* **Mesa de ayuda**: portal del cliente, tickets desde WhatsApp entrante, encuesta de satisfacción.
* **Agenda de turnos**: reserva por portal o link, seña con Mercado Pago, facturar el turno.
* **Órdenes de servicio**: app móvil sin conexión, descuento de stock de materiales, orden desde ticket o contrato.
* **Contratos**: descarga automática de índices BCRA/INDEC, PDF del contrato y firma digital, revisión legal.
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
