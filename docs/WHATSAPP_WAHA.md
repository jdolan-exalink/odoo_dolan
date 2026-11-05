# WhatsApp para Odoo CE con WAHA

**Estado:** integración implementada y probada contra respuestas WAHA simuladas; falta conectar una instancia WAHA real y aceptar visualmente el flujo de vinculación.

## Incluido en `DOLAN_whatsapp`

- Cuenta WAHA por compañía, URL, sesión, estado y claves protegidas para administradores.
- Botones para probar la API, crear e iniciar una sesión y actualizar su estado/QR.
- Botón manual en el contacto para redactar y enviar texto por `POST /api/sendText`.
- Webhook de mensajes con token aleatorio y verificación HMAC-SHA512; los mensajes duplicados no se guardan dos veces.
- Bandeja interna de mensajes con enlace al contacto cuando el teléfono está registrado.
- ACL Odoo 20 `ir.access` y alcance por compañías activas.
- El perfil full y los perfiles DOLAN incluyen el addon; WAHA permanece como servicio separado y autohospedado.

Los adjuntos entrantes se registran con una nota y todavía no se descargan. La integración no importa historial, grupos ni estados de entrega y no envía mensajes automáticos. Las emisiones de texto solo ocurren al confirmar el botón **Enviar mensaje**.

## Configuración requerida

1. Instalar WAHA con su procedimiento Docker y fijar API key y credenciales administrativas seguras.
2. Crear una sesión en **WhatsApp → Conexiones WAHA** e indicar la URL y clave API del servidor.
3. Configurar `web.base.url` con una URL HTTPS pública para que WAHA alcance el webhook.
4. Crear la sesión, iniciarla, consultar el QR y vincular el teléfono desde WhatsApp.
5. Guardar el número internacional del cliente, realizar una prueba acordada y confirmar entrada/salida.

Si WAHA corre en otro contenedor de la misma red Docker, la URL típica es `http://waha:3000`. No se publica su API en interfaces públicas; WAHA recomienda proteger cada petición con `X-Api-Key` y aplicar reglas de red.

## Evidencia

- Prueba de instalación limpia PowerShell: `evidence/installer-powershell-full-e2e-callback-2026-10-30.log`.
- Pruebas de módulo WAHA: `evidence/dolan-whatsapp-1.0-clean-qa-2026-10-30.log`.
- Prueba de instalación limpia Bash: `evidence/installer-bash-full-e2e-callback-2026-10-30.log` (en ejecución al redactar esta versión).

La API comprobada es `POST /api/sendText`; la configuración de eventos y HMAC sigue la documentación oficial de WAHA: [Send messages](https://waha.devlike.pro/docs/how-to/send-messages/), [Receive messages](https://waha.devlike.pro/docs/how-to/receive-messages/), [Events and HMAC](https://waha.devlike.pro/docs/how-to/events/) y [Security](https://waha.devlike.pro/docs/how-to/security/).
