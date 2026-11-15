# Respaldos (`DOLAN_backup`)

Carpeta del Inicio: **Configuraciones**. Estado: beta. Depende de `mail`. Solo administradores.

## Para qué sirve

Tener respaldos de la base y de los adjuntos hechos por Odoo todos los días, saber si salieron bien y comprobar
que se pueden restaurar.

## Cómo se usa

* Se hace un respaldo por día (tarea programada) en formato .zip con la base y los adjuntos. **Respaldar ahora**
  hace uno en el momento.
* **Opciones**: carpeta del servidor donde se guardan (por defecto `<data_dir>/dolan_backups/<base>`), cuántos
  conservar (7 por defecto; los más viejos se borran) y hora del próximo respaldo.
* **Descargar** baja el archivo. Conviene guardar una copia fuera del servidor.
* **Probar restauración** restaura el respaldo en una base temporal (`<base>_prueba_restauracion`), cuenta los
  módulos instalados y la borra. Si encuentra menos del 90 % de los módulos de hoy, marca la prueba como fallida.
* Cada respaldo queda con fecha, tamaño, duración, origen (programado o manual), estado y el error si falló.

## Requisito: versión de pg_dump

`pg_dump` tiene que ser de la misma versión de PostgreSQL que la base o más nueva. Si es más viejo, el respaldo se
marca con error y explica qué hacer, sin intentar el volcado. La imagen de Odoo ahora instala el cliente de
PostgreSQL 17 (Dockerfile). **En la PC local y en 10.1.1.9 hay que reconstruir la imagen** para que los respaldos
funcionen; 10.1.1.68 ya tiene `pg_dump` 18.

## Pruebas automáticas

5 tests (con el volcado simulado): respaldo y retención, respaldo con error registrado, `pg_dump` viejo,
resultado de la prueba de restauración y acceso solo para administradores.

## Pendiente

* Copia automática fuera del servidor (S3, Google Drive o NAS).
* Cifrado del archivo de respaldo.
