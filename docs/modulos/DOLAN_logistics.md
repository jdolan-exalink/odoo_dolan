# Logística (`DOLAN_logistics`)

Carpeta del Inicio: **Logística**. Estado: beta. Depende de `stock` y `mail`. Capacidad del PRD: F22.
Un módulo con tres apps: **Preparación de pedidos**, **Rutas y reparto** y **Prueba de entrega**.

## Flujo

1. **Preparación de pedidos**: una oleada junta entregas listas (reservadas) que todavía no se prepararon
   (*Agregar entregas listas*). Al *Empezar a preparar* suma lo que hay que buscar por producto, con la ubicación
   donde más stock hay. El preparador carga lo juntado (o *Todo juntado*), o lee con el lector el código de barras
   (o el código interno) de cada producto en el campo **Escanear**: cada lectura suma una unidad y avisa si el código
   no es de la oleada o si sobra mercadería. Al *Terminar*:
   * las entregas que se pueden completar con lo juntado (de la más antigua a la más nueva) quedan **Preparadas**;
   * las que no, vuelven a quedar libres y se anotan en la oleada como faltantes.
2. **Rutas y reparto**: la hoja de ruta (fecha, repartidor, vehículo) toma las entregas preparadas que no están en
   otra ruta abierta, en orden de visita. Estados: *Armando → Cargada → En reparto → Rendida*. Muestra lo que hay
   que cobrar, lo cobrado, lo cobrado en efectivo, lo que rinde el repartidor y la diferencia. No se cierra con
   paradas sin resultado.
   * **Ver en el mapa** abre el recorrido en Google Maps desde la empresa, pasando por las paradas pendientes en
     orden (hasta 9 paradas intermedias en el link).
   * **Ordenar por cercanía** ordena las paradas desde la empresa, cada una a la más cercana de la anterior. Usa las
     coordenadas del contacto (las de la empresa y las de cada cliente).
3. **Prueba de entrega** (pantalla del repartidor, por parada): quién recibió y su DNI, **firma o foto**,
   ubicación, cobro (importe y medio) y observaciones.
   * **Entregada**: valida la entrega en Inventario.
   * **Entrega parcial**: se cargan las cantidades entregadas; se valida eso y lo que falta queda en un pedido
     pendiente.
   * **Rechazada**: con motivo (ausente, no aceptó, dañada, dirección incorrecta, no pudo pagar); la entrega queda
     disponible para otra ruta.

## Módulos puente (se instalan solos)

* **`DOLAN_logistics_treasury`** (con Caja y Tesorería): la hoja de ruta tiene **Caja de rendición**. Al rendir y
  cerrar, lo cobrado en efectivo se asienta en el diario de esa caja contra la cuenta a cobrar de cada cliente y se
  concilia con sus deudas abiertas, de la más vieja a la más nueva. La caja tiene que tener un turno abierto; el
  efectivo entra a ese turno y se cuenta en su arqueo (la diferencia con lo rendido aparece ahí).
* **`DOLAN_logistics_whatsapp`** (con DOLAN WhatsApp): opción **Avisar por WhatsApp al entregar** en la hoja de ruta
  (viene marcada si la empresa tiene «Avisar las entregas por WhatsApp» en su ficha). Al entregar, total o parcial,
  le manda al cliente el número de pedido y quién recibió. Si el envío falla, la entrega se registra igual y la
  parada muestra el error.

## Permisos

* **Repartidor**: ve solo sus hojas de ruta y registra resultado, prueba y cobro en sus paradas.
* **Responsable de logística** (incluido en los responsables de Inventario): arma oleadas y rutas y las cierra.
* Los usuarios de Inventario pueden trabajar las oleadas de preparación. Todo filtrado por empresa.

## Pruebas automáticas

8 tests: oleada que suma por producto y prepara solo las entregas completas, entrega total con prueba y
rendición, entrega parcial con pedido pendiente, rechazo con motivo y reasignación, ruta que no cierra con
pendientes, visibilidad entre repartidores, lectura de códigos y orden por cercanía con link de mapa.
Puentes: 2 tests de rendición a caja (asiento, conciliación, exige turno abierto) y 3 del aviso por WhatsApp
(envío, error que no frena la entrega, opción apagada).

## Pendiente

* Preparación por zona del depósito.
* Tomar la ubicación del celular automáticamente al entregar y buscar coordenadas de los clientes sin cargarlas a
  mano (geolocalización).
* Recibos de cobro desde la parada y rendición de transferencias, cheques y Mercado Pago (hoy solo el efectivo
  pasa a Caja y Tesorería).
