# Sucursales (`DOLAN_branch`)

Carpeta del Inicio: **Configuraciones**. Estado: beta. Depende de `account` y `stock`. Para administradores.

## Para qué sirve

Separar los locales o depósitos de una misma empresa (mismo CUIT) sin crear otra empresa en Odoo. Cada sucursal
tiene su depósito, sus diarios, su lista de precios y sus usuarios, y las facturas y remitos quedan marcados con la
sucursal para filtrarlos y agruparlos.

## Cómo se usa

1. **Sucursales → Nueva**: nombre, código (único por empresa), dirección, responsable, depósito (cada depósito
   pertenece a una sola sucursal), diarios de venta y cobro, y lista de precios.
2. En cada usuario, pestaña **Sucursales**: en cuáles puede trabajar y cuál es la suya por defecto.
3. Las facturas toman la sucursal del diario; si el diario no tiene sucursal, la del usuario. Se puede cambiar a
   mano mientras están en borrador.
4. Los remitos toman la sucursal del depósito del tipo de operación.
5. Filtros y agrupaciones **Sucursal** en facturas y en operaciones de inventario; desde la sucursal, el botón
   **Comprobantes** abre sus facturas.

## Permisos

Todos los usuarios internos ven las sucursales; solo Administración / Ajustes las crea o cambia.

## Pruebas automáticas

5 tests: factura con la sucursal del diario y, si el diario no tiene, la del usuario; remito con la sucursal del
depósito; sucursal por defecto fuera de las permitidas y código repetido rechazados; conteo de comprobantes.

## Pendiente

* Numeración de comprobantes y punto de venta de ARCA por sucursal.
* Permisos que limiten lo que ve cada usuario a sus sucursales (hoy es una marca para filtrar, no una restricción).
* Sucursal en el POS y en los reportes de Rentabilidad, Flujo de caja y Caja y Tesorería.
