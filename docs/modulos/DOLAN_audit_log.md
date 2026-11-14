# Auditoría (`DOLAN_audit_log`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `account` y `product`.
Capacidad del PRD: F15 (sección 6, Auditoría y autorizaciones).

## Para qué sirve

Saber quién cambió qué y cuándo en operaciones sensibles, con el valor anterior y el nuevo.

## Qué registra (configurable en *Qué se audita*)

| Regla | Modelo | Campos | Altas / Bajas |
|---|---|---|---|
| CUIT de contactos | Contactos | CUIT | bajas |
| Cuentas bancarias | Cuentas bancarias | número, banco, titular, contacto | altas y bajas |
| Precio y costo de productos | Productos | precio de venta, costo | bajas |
| Ítems de listas de precios | Ítems de lista | precio fijo, descuento | altas y bajas |
| Anulación y vuelta a borrador | Comprobantes | estado | bajas |
| Pagos y cobros | Pagos | importe, estado, contacto | altas y bajas |
| Conciliaciones | Conciliaciones parciales | importe, apuntes | altas y bajas |
| Usuarios y permisos | Usuarios | grupos, usuario, activo | altas y bajas |

Cada registro guarda usuario, fecha, empresa, documento, operación, cambios (antes → después) y el **motivo** si
la operación se hizo con el contexto `dolan_audit_reason`.

## Garantías

* La bitácora solo la escribe el sistema; nadie la puede modificar ni borrar desde la interfaz ni por RPC.
* Nunca se guardan valores de campos de contraseñas, claves, tokens, firmas, tarjetas, imágenes o HTML.
* Los cambios en campos no auditados no generan registros.

## Permisos

Grupo **Auditor** (incluido en contadores y administradores): consulta la bitácora de sus empresas. Las reglas las
ajusta el administrador.

## Pruebas automáticas

7 tests: cambio de CUIT con antes, después, usuario y motivo; campos no auditados; precio y borrado de producto;
alta de cuenta bancaria; inalterabilidad; regla desactivada; usuarios y permisos.

## Pendiente

* Pedir motivo (y aprobación) en la interfaz para operaciones sensibles, no solo por contexto.
* Descuentos excepcionales y devoluciones del POS y de pedidos de venta (necesita un módulo puente con `sale` y
  `point_of_sale`).
* Exportar la bitácora firmada para entregar a un auditor.
