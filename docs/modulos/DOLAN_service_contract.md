# Contratos (`DOLAN_service_contract`)

Carpeta del Inicio: **Servicios**. Estado: beta. Depende de `mail` y `DOLAN_subscription`.
Perfiles: Servicios y Completo.

## Para qué sirve

Administrar contratos de servicio o alquiler: vigencia, renovación, aviso de fin y ajuste periódico de precio.
No factura por su cuenta: si el contrato está vinculado a una suscripción, el ajuste actualiza los precios de la
suscripción y la facturación sigue siendo la de **Suscripciones**.

## Cómo se usa

1. Cargar los valores mensuales de los índices en **Índices de ajuste** (vienen creados IPC, ICL, CER y CAC, sin
   valores). El mes se guarda siempre como el primer día.
2. Crear el contrato: cliente, objeto, inicio y fin, importe inicial, documento firmado, condiciones.
   * Ajuste: *sin ajuste*, *porcentaje fijo por período* o *índice*, cada cuántos meses y, para índices, el
     desfase de publicación (por defecto 1 mes).
   * Renovación automática por N meses y días de aviso antes del fin.
3. **Poner en vigencia**. El importe vigente arranca en el inicial.
4. **Aplicar ajuste** (o lo hace la tarea diaria al llegar la fecha). Factor con índice = índice del mes de
   ajuste menos el desfase / índice del mes del ajuste anterior (o del inicio) menos el desfase. Si falta un valor
   no ajusta y crea una actividad al responsable.

Tarea diaria: aplica ajustes vencidos, crea la actividad de aviso de fin y renueva (o marca *Vencido*) los
contratos que pasaron su fecha de fin.

## Modelos

| Modelo | Qué guarda |
|---|---|
| `dolan.contract` | Contrato `CT-año-####`, vigencia, renovación, importes, ajuste, suscripción. |
| `dolan.contract.adjustment` | Historial: fecha, índices, factor, importes antes y después. |
| `dolan.contract.index` / `.value` | Índices y sus valores mensuales. |

## Permisos

* **Usuario**: consulta contratos e índices.
* **Responsable**: crea contratos, carga índices y aplica ajustes. Filtrado por empresa.

## Pruebas automáticas

8 tests: normalización del mes, ajuste por índice en dos períodos, falta de índice, porcentaje, actualización de
la suscripción, renovación y vencimiento, aviso de fin, fechas y permisos.

## Pendiente

* Descarga automática de índices (BCRA para ICL y CER, INDEC para IPC).
* Plantilla del contrato en PDF y firma digital.
* Validación legal de las cláusulas de ajuste (Ley de alquileres vigente) con un profesional.
