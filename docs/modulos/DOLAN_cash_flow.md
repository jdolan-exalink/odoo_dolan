# Flujo de caja (`DOLAN_cash_flow`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `account`. Para contadores
(`account.group_account_manager`).

## Para qué sirve

Ver cuánta caja va a haber en las próximas semanas o meses y detectar a tiempo los períodos en negativo.

## Cómo se calcula

* **Saldo inicial**: saldo contable de las cuentas de los diarios de caja y bancos a la fecha desde.
* **Entradas**: comprobantes a cobrar abiertos según vencimiento; lo vencido entra según el escenario (porcentaje
  que se espera cobrar y en cuántos días). Cheques de terceros en cartera según su fecha de cobro. Previsiones
  manuales de entrada.
* **Salidas**: comprobantes a pagar abiertos según vencimiento (lo vencido, en el primer período). Cheques propios
  entregados según su fecha de débito. Previsiones manuales de salida.
* Los anticipos (de clientes o a proveedores) no se cuentan como entrada ni salida futura.
* Los cheques ya tienen su pago registrado, por eso no se cuentan dos veces con las cobranzas.

## Cómo se usa

1. **Previsiones**: cargar lo que todavía no tiene comprobante (sueldos, alquileres, impuestos, cuotas de
   préstamos), con repetición mensual si corresponde.
2. **Proyección**: elegir semanal o mensual, cantidad de períodos y el escenario de cobro; *Calcular*. Se ve en
   lista (con saldos en rojo cuando son negativos), gráfico de línea y tabla dinámica.

## Pruebas automáticas

3 tests: proyección con cobranzas, pagos, vencido según escenario y previsión; previsión mensual repetida y
períodos negativos; anticipos que no son entradas.

## Pendiente

* Sumar como entradas previstas la facturación futura de Suscripciones y Contratos.
* Guardar escenarios para compararlos.
* Monedas extranjeras (hoy todo en la moneda de la empresa).
