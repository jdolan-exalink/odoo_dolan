# DOLAN UI 3.1 — migración

Versión del módulo: `20.0.2.50.0`.

La migración es idempotente: configura el perfil global heredado para instalaciones existentes, marca como `legacy` las preferencias que reciben el valor inicial del campo nuevo y crea preferencias `legacy` solo para usuarios internos existentes que aún no tenían fila. No cambia modo, paleta, iconos, densidad, colores de compañía, carpetas, favoritos ni preferencias de Mi Espacio.

Instalaciones nuevas usan Enterprise Classic desde el hook posterior a la instalación. Usuarios creados después de la actualización heredan el perfil global. Reversión: restaurar backup antes de actualizar y volver a la versión anterior del módulo; no se borran datos de preferencias.
