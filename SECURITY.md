# Política de seguridad de DOLAN

## Versiones con soporte

- La línea soportada actualmente es DOLAN sobre Odoo Community 20.0.
- No se declara compatibilidad con Odoo 21 hasta completar una matriz de pruebas y publicar una release compatible.
- Las imágenes o paquetes de una release se identifican por versión y digest; una etiqueta móvil no se considera una release reproducible.

## Reportar una vulnerabilidad

No publiques credenciales, datos de clientes ni detalles explotables en un issue público. Usá la opción **Private vulnerability reporting** del repositorio si está habilitada. Si no aparece, contactá en privado a los mantenedores desde el perfil de GitHub del proyecto y pedí un canal seguro para el reporte.

Incluí el componente y versión afectados, impacto, pasos mínimos para reproducir y una forma segura de contacto. No adjuntes bases de datos, certificados, tokens ni información personal.

Los mantenedores procurarán confirmar recepción dentro de cinco días hábiles y comunicar la evaluación inicial dentro de diez. Los plazos de corrección dependen de la gravedad, posibilidad de mitigación y disponibilidad de una actualización segura; no se garantiza un SLA contractual.

## Manejo de secretos y datos

- Certificados, claves privadas, `.env`, bases, filestore, facturas de clientes, backups y logs operativos no forman parte del repositorio ni de los artefactos públicos.
- Si un secreto se expone, revocalo o rotalo primero; borrar el archivo del último commit no invalida copias del historial.
- Las pruebas automatizadas usan datos sintéticos y no solicitan CAE, no cobran, ni envían mensajes externos.

## Releases

Cada release debe publicar el commit de origen, SBOM SPDX, notices de terceros, digest de imagen y resultado de CI. La lista de dependencias y licencias debe corresponder al artefacto construido, no sólo a los archivos declarativos.
