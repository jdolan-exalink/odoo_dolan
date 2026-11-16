# Presupuesto financiero (`DOLAN_budget`)

Carpeta del Inicio: **Gestión y Análisis**. Estado: beta. Depende de `account`. Para contadores.

## Para qué sirve

Presupuestar por cuenta contable y mes y comparar contra lo real de la contabilidad.

## Cómo se usa

1. Crear el presupuesto (nombre, desde, hasta).
2. Cargar líneas a mano (cuenta, mes, importe) o con **Carga rápida**: repartir un importe del período en partes
   iguales por mes, o tomar lo real del mismo mes del año anterior con un porcentaje de ajuste.
3. **Aprobar**; al **Cerrar** ya no se modifica.
4. **Contra real**: tabla dinámica por cuenta y mes con presupuestado, real, desvío y ejecución %, gráfico y lista.

Los ingresos y las demás cuentas de saldo acreedor se muestran en positivo, igual que los gastos, para que el
desvío se lea igual: positivo = se superó lo presupuestado.

## Pruebas automáticas

4 tests: carga en partes iguales y comparación con lo real, ingresos en positivo, carga desde el año anterior con
ajuste y bloqueo del presupuesto cerrado.

## Pendiente

* Presupuesto por centro de costo (cuentas analíticas).
* Alerta cuando una cuenta supera lo presupuestado (se puede sumar como condición de Alertas).
