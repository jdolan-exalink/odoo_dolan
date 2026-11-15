# Logística (`DOLAN_logistics`)

Carpeta del Inicio: **Logística**. Estado: beta. Depende de `stock` y `mail`. Capacidad del PRD: F22.
Un módulo con tres apps: **Preparación de pedidos**, **Rutas y reparto** y **Prueba de entrega**.

## Flujo

1. **Preparación de pedidos**: una oleada junta entregas listas (reservadas) que todavía no se prepararon
   (*Agregar entregas listas*). Al *Empezar a preparar* suma lo que hay que buscar por producto, con la ubicación
   donde más stock hay. El preparador carga lo juntado (o *Todo juntado*) y al *Terminar*:
   * las entregas que se pueden completar con lo juntado (de la más antigua a la más nueva) quedan **Preparadas**;
   * las que no, vuelven a quedar libres y se anotan en la oleada como faltantes.
2. **Rutas y reparto**: la hoja de ruta (fecha, repartidor, vehículo) toma las entregas preparadas que no están en
   otra ruta abierta, en orden de visita. Estados: *Armando → Cargada → En reparto → Rendida*. Muestra lo que hay
   que cobrar, lo cobrado, lo cobrado en efectivo, lo que rinde el repartidor y la diferencia. No se cierra con
   paradas sin resultado.
3. **Prueba de entrega** (pantalla del repartidor, por parada): quién recibió y su DNI, **firma o foto**,
   ubicación, cobro (importe y medio) y observaciones.
   * **Entregada**: valida la entrega en Inventario.
   * **Entrega parcial**: se cargan las cantidades entregadas; se valida eso y lo que falta queda en un pedido
     pendiente.
   * **Rechazada**: con motivo (ausente, no aceptó, dañada, dirección incorrecta, no pudo pagar); la entrega queda
     disponible para otra ruta.

## Permisos

* **Repartidor**: ve solo sus hojas de ruta y registra resultado, prueba y cobro en sus paradas.
* **Responsable de logística** (incluido en los responsables de Inventario): arma oleadas y rutas y las cierra.
* Los usuarios de Inventario pueden trabajar las oleadas de preparación. Todo filtrado por empresa.

## Pruebas automáticas

6 tests: oleada que suma por producto y prepara solo las entregas completas, entrega total con prueba y
rendición, entrega parcial con pedido pendiente, rechazo con motivo y reasignación, ruta que no cierra con
pendientes, y visibilidad entre repartidores.

## Pendiente

* Control de preparación con lector de códigos de barras y preparación por zona.
* Ordenar paradas por cercanía en un mapa y tomar la ubicación del celular automáticamente.
* Rendición del efectivo a Caja y Tesorería y recibos de cobro desde la parada (hoy el cobro queda registrado en
  la parada y en la rendición de la ruta, sin asiento).
* Aviso al cliente por WhatsApp al entregar.
