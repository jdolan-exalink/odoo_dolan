# DOLAN Mi Espacio 3.0 — Diseño

## Principios

- Evolucionar `DOLAN_theme/static/src/xml/dolan_app_drawer.xml` en la pestaña `mine`; no crear una acción o dashboard aislado.
- Reutilizar tokens, `DolanIcon`, preferencias de tema y clases de accesibilidad del theme.
- Diseñar para claro, oscuro, contraste alto y estilos de icono configurados por el usuario.
- Mantener fondo, tarjeta, borde y texto en variables del tema; no fijar colores solo para modo oscuro.

## Estructura de la pantalla

1. Cabecera contextual y controles de edición.
2. Píldoras de espacios/áreas y modos de indicadores.
3. POS destacado y accesos rápidos compactos.
4. Atención y resumen en dos columnas amplias.
5. Otros indicadores y actividad reciente en dos columnas.

## Responsive

| Ancho | Distribución |
|---|---|
| ≥1440 | POS + accesos en fila; atención/resumen y otros/actividad en dos columnas |
| 1024–1439 | Grillas reducidas, sin overflow horizontal |
| 768–1023 | Secciones apiladas con grillas de 2 columnas |
| <768 | Una columna; alertas antes de secundarios; controles táctiles |

## Interacción

- Cambiar espacio solo cambia el filtro de presentación y guarda la preferencia del usuario.
- Ocultar/leer/posponer alerta se refleja inmediatamente y se persiste en servidor.
- Los widgets independientes tienen carga, vacío y error local.
- El editor ofrece controles de mover arriba/abajo y tamaños además de pointer drag.
- El POS no crea ni cierra sesiones; la apertura se limita a configuraciones que el usuario puede leer.

## Iconografía

Iconos de aplicación y accesos usan catálogo semántico DOLAN según el estilo elegido. Iconos de estados/acciones usan Tabler/DolanIcon. Cualquier acceso a función opcional verifica que la acción o modelo exista antes de renderizarlo.
