# Caja y Tesorería (`DOLAN_treasury`)

Carpeta del Inicio: **Facturación y Finanzas** (y *Turnos de caja* en **Punto de venta y caja**). Estado: beta.
Depende de `account` y `mail`. Capacidad del PRD: F08 (sección 6, Caja y tesorería).

## Para qué sirve

Controlar el efectivo físico de cada caja (central, de sucursal, de punto de venta o caja chica) por turnos y
cajeros, con arqueo por billetes y monedas, y dejar cada movimiento asentado en la contabilidad.

## Principio

Cada caja tiene su **diario de efectivo**. El saldo esperado de la caja es el **saldo contable** de la cuenta de ese
diario: la caja física se compara contra la contabilidad, separada de los bancos. Si se usa el diario de efectivo
del POS, las ventas en efectivo del POS entran solas en ese saldo.

## Cómo se usa

1. **Configuración**: crear las cajas (diario de efectivo, cajeros habilitados, fondo fijo, tolerancia de
   diferencia y cuentas de faltantes y sobrantes), los **motivos** de ingreso y retiro con su cuenta contable
   (aporte, retiro de socio, gasto, pago en efectivo) y revisar **Billetes y monedas** (vienen los de pesos).
2. **Abrir turno**: el cajero indica lo que cuenta al abrir; si no coincide con el saldo contable queda anotado.
   Solo puede haber un turno abierto por caja.
3. **Movimientos**: ingreso, retiro o gasto (con motivo) y transferencia a otra caja (rendición a la central).
   Al *Asentar* se genera el asiento; un movimiento asentado no se modifica ni se borra.
4. **Arqueo**: *Cargar billetes y monedas* y completar cantidades.
5. **Cerrar turno**: compara lo contado con el saldo contable.
   * Diferencia dentro de la tolerancia: se asienta sola contra sobrantes o faltantes y el turno queda cerrado.
   * Mayor a la tolerancia: el turno queda *Diferencia a aprobar*, se crea una actividad al tesorero, que escribe
     la explicación y la **aprueba** (se asienta) o lo **devuelve para recontar**.

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.cash.box` | Caja: diario, cajeros, fondo fijo, tolerancia, cuentas de diferencia. |
| `dolan.cash.session` | Turno: cajero, apertura, arqueo, saldo esperado, diferencia, aprobación. |
| `dolan.cash.move` | Ingreso, retiro o transferencia con su asiento. |
| `dolan.cash.count` | Línea de arqueo por denominación. |
| `dolan.cash.denomination` | Billetes y monedas por moneda. |
| `dolan.cash.reason` | Motivos con cuenta de contrapartida. |

## Permisos

* **Cajero**: ve las cajas donde está habilitado y solo sus turnos y movimientos.
* **Tesorero** (también los contadores): todas las cajas y turnos de sus empresas, configura y aprueba diferencias.

## Pruebas automáticas

8 tests: turno completo sin diferencia, diferencia chica asentada sola, diferencia grande con aprobación,
transferencia a la central, un turno abierto por caja y cajeros habilitados, bloqueos de lo asentado y del arqueo
cerrado, diferencia al abrir, y visibilidad entre cajeros.

## Pendiente

* Rendición automática de la sesión del POS a la caja central al cerrarla, y abrir y cerrar el turno desde la
  pantalla del POS.
* Entrega de caja entre turnos con conformidad de ambos cajeros.
* Caja proyectada (cheques y pagos a vencer): app *Flujo de caja* de Gestión y Análisis.
* Cajas por sucursal cuando exista el módulo de Sucursales.
* Monedas extranjeras en una misma caja (hoy cada caja trabaja en la moneda de la empresa).
