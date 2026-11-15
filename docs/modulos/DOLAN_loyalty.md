# Fidelización (`DOLAN_loyalty`)

Carpeta del Inicio: **Comercial**. Estado: beta. Depende de `loyalty` (fidelización de Odoo). Perfiles Comercio y
Completo.

## Para qué sirve

Premiar a los clientes frecuentes con puntos, tarjetas de regalo y cupones, usando el motor de fidelización de
Odoo pero con una app propia, en castellano y armada en pesos.

## Cómo se usa

1. **Fidelización → Configuración → Configurar** (administradores): nombre del programa, cada cuántos pesos se
   gana un punto (por defecto $1.000), cuánto vale un punto al canjear (por defecto $10), mínimo de puntos para
   canjear (100) y a los cuántos días vencen los puntos (365; 0 = no vencen). Opcionalmente crea también la
   **tarjeta de regalo**.
2. Al vender a un cliente identificado (en Ventas o en el POS) los puntos se suman solos; el canje aparece como
   premio en el pedido o en el POS cuando el cliente tiene el mínimo.
3. **Saldos de puntos**: tarjetas de puntos por cliente. En la ficha del cliente, botón **Puntos** con su saldo.
4. **Movimientos**: puntos emitidos y canjeados por mes y tipo de programa (tabla, gráfico y lista), con filtro de
   los que vencen este mes.
5. **Programas** y **Tarjetas de regalo y billetera** abren las pantallas de Odoo para ajustes finos (productos
   que suman, premios en producto, comunicación por correo).

## Cómo convive con Promociones

`sale_loyalty` y `pos_loyalty` se instalan solos cuando están Ventas o el POS. Los puntos se calculan sobre lo
que el cliente paga, después de los descuentos de Promociones (`DOLAN_discount_engine`), así que una promoción
no regala puntos de más.

## Pruebas automáticas

4 tests: programa de puntos en pesos con vencimiento y tarjeta de regalo, asistente sin tarjeta de regalo y con
valores inválidos, saldo de puntos del cliente y configuración solo para administradores.

## Pendiente

* Aviso de puntos ganados o por vencer por WhatsApp.
* Puntos extra por cumpleaños o por categoría de cliente.
* Regla para que un premio de puntos no se combine con una promoción (habría que sumarla a Promociones).
