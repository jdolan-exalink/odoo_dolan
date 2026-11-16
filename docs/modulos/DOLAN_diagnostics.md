# Diagnóstico (`DOLAN_diagnostics`)

Carpeta del Inicio: **Configuraciones**. Estado: beta. Depende de `mail`. Solo administradores.

## Para qué sirve

Ver la salud del sistema en una lista corta, ordenada con los problemas primero, cada uno con qué hacer. No cambia
nada: solo informa.

## Qué revisa

| Tema | Revisar / Error cuando... |
|---|---|
| Módulos | hay módulos instalados con una versión más nueva en el servidor sin actualizar, o quedaron a medias |
| Tareas programadas | una tarea falla seguido, o muchas están atrasadas más de 3 horas (no corren los workers de cron) |
| Disco | queda menos del 20 % (revisar) o del 10 % (error) libre en el disco de datos de Odoo |
| Base de datos | informa versión de PostgreSQL, tamaño y cantidad de adjuntos |
| Respaldos | `pg_dump` más viejo que la base; sin Respaldos instalado; último respaldo de hace más de 2 días (revisar) o 7 (error) |
| Certificado ARCA | vence en menos de 30 días o venció |
| Correo | no hay servidor de salida o hay correos con error |

Se revisa una vez por día y con **Revisar ahora**. Las filas con registro (tarea, respaldo, empresa) tienen un
botón para abrirlo.

## Pruebas automáticas

5 tests: una fila por tema, umbrales de disco, tarea con fallas y `pg_dump` viejo, revisión rota que no frena las
demás y acceso solo para administradores.

## Pendiente

* Tamaño del log, workers y memoria del servidor.
* Versión de la imagen instalada contra la última publicada.
* Avisar por Alertas cuando algo pasa a error.
