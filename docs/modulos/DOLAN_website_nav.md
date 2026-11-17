# Web ↔ Escritorio (`DOLAN_website_nav`)

Módulo puente: se instala solo cuando están el sitio web de Odoo (`website`) y `DOLAN_theme`. Donde no hay sitio web
(por ejemplo la 10.1.1.9, sin tienda) no se instala ni aparece nada.

## Qué hace

* **Del sitio web al sistema**: Odoo muestra a los usuarios internos un botón en la esquina superior izquierda del
  sitio que abre una lista plana de menús. Acá ese botón dice **Escritorio** y lleva directo a `/odoo`, el
  Escritorio DOLAN con sus carpetas y apps. El botón **Editor** sigue igual para quien edita la web.
* **Del sistema al sitio web**: botón con el ícono de globo en la barra superior («Ir al sitio web») que abre la
  web en la misma pestaña. Desde ahí, **Escritorio** vuelve.

Es el mismo recorrido que propone Odoo (la web y el sistema son dos pantallas con un acceso fijo en cada una), con
nuestro Escritorio como destino; el código es propio.

## Pruebas automáticas

2 tests: un usuario interno ve **Escritorio** con link a `/odoo` y sin la lista de menús; un visitante no ve
ningún botón del sistema.
