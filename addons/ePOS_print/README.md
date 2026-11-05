# ePOS Print

App de configuración de las impresoras de recibos y preparación de Odoo POS 20.
Usa los modelos nativos `pos.printer` y `pos.config`, y la comunicación ePOS que
Odoo realiza desde el navegador del POS.

## Configurar

1. Abrí **ePOS Print → Configurar por Punto de Venta**.
2. Editá el POS y activá **Impresoras de recibos** o **Impresoras de cocina y comandas**.
3. Creá/seleccioná impresoras. Elegí **Recibo** o **Preparación**, ingresá IP/host,
   ancho de papel y, para cocina, categorías que debe imprimir.
4. En **ePOS Print → Impresoras**, abrí una impresora y pulsá **Imprimir ticket de
   prueba**. La acción muestra un LED, registra el último resultado y solo imprime
   cuando confirmás el botón de prueba. Desde la configuración del POS, la prueba
   nativa de recibos puede imprimir en todas las impresoras asignadas.
5. Recargá la sesión POS después de guardar cambios.

El pedido de impresión sale del navegador que tiene abierto el POS; la PC/tablet
debe estar en la red de la impresora. `Use Local Network Access` permite el modo
HTTP donde el navegador y la impresora lo admiten. En modo HTTPS sin LNA, el
navegador necesita confiar en el certificado HTTPS de la impresora.

## Compatibilidad

Odoo envía al driver nativo Epson ePOS XML con imágenes rasterizadas. Las Epson
compatibles pueden recibirlo directamente. Para una impresora ESC/POS genérica,
el servicio `services/escpos-bridge` incluido en este repositorio recibe ese XML,
lo convierte a ESC/POS y lo envía por TCP al destino fijo configurado en Docker.
El navegador no abre conexiones TCP crudas.

### Xprinter XP-E200M (58 mm)

En `.env`, configurá `EPOS_BRIDGE_PRINTER_HOST`, `EPOS_BRIDGE_PRINTER_PORT=9100`
y `EPOS_BRIDGE_RASTER_WIDTH_DOTS=384`. El puente escucha en el host en el puerto
`EPOS_BRIDGE_PORT` (por defecto 8765); levantalo con `docker compose up -d --build
escpos_bridge`. El servicio no ofrece una API para modificar el destino desde la
red: el host y el puerto de la impresora son variables de despliegue. Solo acepta
peticiones ePOS del origen Odoo incluido en `EPOS_BRIDGE_ALLOWED_ORIGINS`, valida
el `devid=local_printer`, limita el tamaño del XML y permite únicamente etiquetas
de impresión conocidas.

En **ePOS Print → Impresoras**, configurá el tipo **ESC/POS por puente**, marcá
**Acceso a red local (LNA)** y como IP/puerto ePOS ingresá la dirección del host
del puente que alcanza el navegador del POS, por ejemplo `192.168.1.20:8765`. En
**Impresora ESC/POS de destino** se muestra `192.168.1.50:9100`; el destino efectivo
lo determina la configuración del servicio, no el formulario de Odoo. Para el
Odoo local, usá `127.0.0.1:8765` si el navegador y Docker corren en esa misma PC.

Las impresoras de cocina usan el mismo flujo: asigná la impresora a las
categorías correspondientes en la configuración del POS. Para varias impresoras
de destino se requiere una instancia/configuración de puente por destino.

El puente responde los estados ePOS como éxito de envío, pero ESC/POS por TCP no
devuelve estado real de papel/tapa. Revisá la impresora para confirmar el papel.
No publiques el puerto del puente en Internet; limitá el acceso con firewall y
conservá la lista de orígenes permitidos acotada a las URL de Odoo.
