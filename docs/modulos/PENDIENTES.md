# Pendientes

Actualizado el 15/11/2026. Lo que está en desarrollo sigue el orden que pidió Juan: Servicios (hecho),
Facturación y Finanzas (hecho: Cuentas corrientes y Caja y Tesorería), Inventario y Compras (hecho: Costos; el resto de la carpeta ya eran apps de Odoo), Gestión y Análisis (hecho), Logística (hecho), Configuraciones (hecho), Comercial (hecho). Todas las apps del catálogo tienen módulo.

## Apps del catálogo sin implementación propia

Ninguna. Decisiones abiertas:

* **Tienda online** instala el sitio web de Odoo (página pública en `/` y `/shop`). Está solo en el perfil
  Completo; falta que Juan decida si se instala en los servidores de producción y con qué dominio.
* **Fidelización** y **Promociones** conviven: los puntos se calculan sobre lo que el cliente paga después de los
  descuentos de Promociones. Si hace falta que un premio de puntos no se combine con una promoción, hay que
  sumarlo al motor de Promociones.

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
* **Logística**: lector de códigos en la preparación, mapa y ubicación automática, rendición a Caja y
  Tesorería con recibos, aviso por WhatsApp al entregar.
* **Flujo de caja**: suscripciones y contratos como entradas previstas, escenarios guardados, monedas extranjeras.
* **Rentabilidad**: margen por sucursal, costo con gastos de importación.
* **Auditoría**: motivo y aprobación en la interfaz, descuentos y devoluciones de POS y ventas, exportación firmada.
* **Alertas**: aviso por WhatsApp, resumen diario por correo.
* **Presupuesto financiero**: por centro de costo, alerta de cuenta excedida.
* **Sucursales**: numeración de comprobantes y punto de venta ARCA por sucursal, permisos que limiten los
  datos a la sucursal del usuario, sucursal en POS y en los reportes de Rentabilidad y Flujo de caja.
* **Integraciones**: bancos e Interbanking, historial de caídas, aviso por Alertas cuando una conexión falla.
* **Importaciones**: proveedores con saldo en dólares, listas de precios, cheques en cartera, lotes y series.
* **Respaldos**: copia automática fuera del servidor (S3, Google Drive o NAS) y cifrado del archivo.
  **Importante**: en la PC local y en 10.1.1.9 la imagen tiene `pg_dump` 15 y la base es PostgreSQL 17, así
  que los respaldos fallan hasta reconstruir la imagen con el Dockerfile nuevo (10.1.1.68 ya tiene `pg_dump` 18).
* **Diagnóstico**: tamaño del log, workers y memoria, versión de la imagen contra la última publicada.
* **Fidelización**: aviso de puntos por WhatsApp, puntos por cumpleaños o por categoría de cliente, reporte de
  puntos por vencer.
* **Tienda online**: promociones del motor DOLAN en la web (hoy son solo del POS), envío con costo por zona,
  sincronización de precios con Listas de precios DOLAN, plantilla visual de la tienda.
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
