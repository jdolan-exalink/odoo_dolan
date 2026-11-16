# Integraciones (`DOLAN_integrations`)

Carpeta del Inicio: **Configuraciones**. Estado: beta. Depende de `mail`. Solo administradores.

## Para qué sirve

Ver en una sola pantalla si las conexiones externas están funcionando, en vez de entrar a cada módulo.

## Qué revisa

| Conexión | Bien | Revisar / Error |
|---|---|---|
| Certificado de ARCA (por empresa) | vigente | vence en menos de 30 días / vencido / sin certificado |
| WhatsApp (WAHA) | sesión conectada | sesión en otro estado / último error |
| Terminales Mercado Pago Point y Clover | identificada y con diario | falta vincular, identificador o diario |
| Mercado Libre y Tiendanube | conectada | token vencido / error de sincronización |
| Correo saliente | servidor configurado | sin servidor |
| Cola de correos | sin errores | correos con error de envío |

Solo aparecen las conexiones de los módulos instalados. La revisión automática corre cada hora y no se conecta
afuera; **Probar** usa la prueba de conexión propia de cada integración (y vuelve a revisar). El ícono de
enlace abre la configuración de esa conexión.

## Pruebas automáticas

4 tests: correo sin servidor, cola de correos con error, revisión repetida sin duplicar filas e integraciones de
módulos no instalados que se omiten.

## Pendiente

* Bancos e Interbanking.
* Historial de caídas por conexión.
* Aviso por Alertas cuando una conexión pasa a error.
