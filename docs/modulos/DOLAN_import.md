# Importaciones (`DOLAN_import`)

Carpeta del Inicio: **Configuraciones**. Estado: beta. Depende de `account` y `stock`. Para administradores.

## Para qué sirve

La carga inicial de datos al empezar con el sistema, desde una planilla, con control antes de grabar y la
posibilidad de deshacerla.

## Qué se puede importar

| Tipo | Columnas (las obligatorias con *) |
|---|---|
| Clientes y proveedores | nombre *, cuit, tipo (cliente, proveedor, ambos), email, telefono, calle, ciudad, codigo_postal |
| Productos | nombre *, codigo, codigo_barras, precio_venta, costo, categoria, tipo (producto, servicio, consumible) |
| Saldos de cuenta corriente | cuit_o_nombre *, tipo (cliente o proveedor), importe *, vencimiento, referencia |
| Stock inicial | codigo_o_nombre *, cantidad * |

Acepta Excel (.xlsx) o CSV (separado por coma o punto y coma); los importes pueden venir como `1.250,50`.

## Cómo se usa

1. **Importaciones → Nueva**, elegir el tipo y **Descargar plantilla**.
2. Completar la planilla y subirla. Para saldos: cuenta de apertura, diario y fecha. Para stock: ubicación.
3. **Validar**: muestra cada fila con lo que va a hacer (crear o actualizar) y los errores (CUIT inválido,
   producto inexistente, importe vacío...). Con errores no deja importar.
4. **Importar**. Contactos se buscan por CUIT y productos por código o código de barras: si existen se actualizan.
5. **Revertir** deshace la importación: borra lo creado, vuelve lo actualizado a sus valores anteriores, borra
   el asiento de saldos y ajusta el stock a lo que había (un producto con movimientos se archiva en vez de borrarse).

## Pruebas automáticas

4 tests: contactos con validación, actualización por CUIT y reversión; productos desde Excel con importe en
formato argentino; saldo de cliente y stock inicial con reversión; columna obligatoria faltante.

## Pendiente

* Saldos de proveedores en dólares.
* Listas de precios, cheques en cartera, lotes y números de serie.
