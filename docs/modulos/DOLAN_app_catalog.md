# Catálogo de apps (`DOLAN_app_catalog`)

Carpeta: **Configuraciones**. Depende de `base`, `web` y `DOLAN_theme`. En todos los perfiles del instalador.

## Para qué sirve

Muestra todas las apps previstas de la distribución en carpetas del Inicio. Cada ícono abre la app real si está
instalada y el usuario tiene permiso; si no, una pantalla informativa sin operaciones:

* **Disponible para instalar**: el módulo existe en el servidor pero no está instalado.
* **En desarrollo** / **Planificado**: todavía no hay implementación.

Nunca instala módulos ni crea datos de negocio.

## Cómo se mantiene

* Fuente: `addons/DOLAN_app_catalog/data/app_catalog.json` (clave, nombre, carpeta, menú o acción real, módulo,
  estado, evidencia, prioridad, perfiles, ícono, funcionalidades previstas, criterios de aceptación).
* Después de editarla: `python scripts/build_app_catalog.py`. Genera los menús y acciones, los íconos en las cinco
  familias del theme (con el hash del contenido en el nombre para que el navegador no muestre versiones viejas) y
  las entradas del catálogo de íconos. La CI corre `--check`.
* Glifos de los estilos de máscara: `scripts/app_catalog_glyphs.py`. Ilustraciones de Expresivo 3D y Flat para
  las apps ya implementadas: `scripts/app_catalog_illustrations.py`. El script falla si dos apps comparten ícono.
* Matriz de cobertura: `python scripts/app_catalog_matrix.py` → `docs/audits/MATRIZ_COBERTURA.csv`.

## Carpetas

Se usan las carpetas del Escritorio de DOLAN_theme. Cada ícono del catálogo se ubica una sola vez en la carpeta
del usuario con ese nombre (la crea si falta); si el usuario lo mueve o borra la carpeta, no vuelve. Cuando una
app del catálogo se instala de verdad, la app real ocupa el lugar de su ícono. Las apps reales sueltas solo se
mueven a carpetas si el usuario lo pide (*Catálogo de apps → Opciones → Ordenar mi Escritorio por carpetas*).

## Administración

*Catálogo de apps → Apps*: estado, evidencia, prioridad, módulo, perfiles, y columna *Oculta*.
*Opciones → Visibilidad*: las pantallas informativas para todos, solo administradores o nadie.
El catálogo se vuelve a resolver solo cuando cambia algún módulo instalado.

## Pruebas automáticas

16 tests. Ver también `docs/audits/AUDITORIA_REPO.md`.
