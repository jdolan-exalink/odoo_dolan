# PRD — DOLAN UI 2.1: Icon Studio y personalización visual

**Estado:** propuesta para priorizar; no implementada.  
**Base:** DOLAN UI 2.0, catálogo semántico `app.*`, estilos Fluent locales e iconos originales de Odoo.

## Objetivo

Dar a administradores y usuarios autorizados una vista previa real y segura de la identidad visual, para ajustar iconos y preferencias sin editar archivos ni perder los cambios al actualizar.

## Experiencia

1. **Ajustes → DOLAN UI → Icon Studio** muestra una grilla del launcher con las apps instaladas en la base.
2. Un selector compara Fluent 3D, Flat, Filled, Outline, Original Odoo y los tratamientos disponibles en una vista única.
3. El usuario puede alternar claro/oscuro, escritorio/móvil y fondo para revisar el contraste antes de aplicar.
4. Cada tarjeta permite seleccionar un recurso semántico de la biblioteca instalada, ver sus metadatos, y restaurar el predeterminado.
5. Una barra de cambios enumera diferencias y permite guardar, cancelar o restablecer la configuración.
6. Una sección individual opcional permite guardar estilo, tema, densidad y disposición del launcher por usuario, cuando el administrador lo habilita.

## Alcance funcional

- Vista previa interactiva sin recargar la web completa.
- Asignación de recursos versionados a IDs semánticos; no aceptar URL externas ni rutas libres.
- Persistencia de valores globales administrados y excepciones personales autorizadas.
- Exportar/importar un paquete JSON validado que incluya IDs y overrides, sin contener recursos ejecutables.
- Modo de comparación lado a lado, búsqueda por app, categorías, etiquetas y estado de disponibilidad.
- Restaurar icono original de Odoo o el valor DOLAN recomendado por separado.
- Respetar el selector original Odoo cuando un módulo no tiene asignación semántica.
- Mensajes claros cuando un módulo se instala, desinstala o cambia su XML ID; no reasignar por coincidencias parciales.
- Mantener favoritos, carpetas, drag-and-drop y accesos directos existentes.

## Permisos y compatibilidad

- Solo `base.group_system` administra catálogo, valores globales e importaciones.
- Usuarios comunes solo modifican preferencias personales habilitadas por el administrador.
- Los assets se resuelven desde el bundle local y con validación de SHA, SVG seguro y licencia registrada.
- Las claves antiguas `fluent` y `tabler` se convierten de forma compatible; no se borran preferencias ni overrides en upgrades.
- Los valores exportados incluyen versión de esquema y se migran de forma explícita.

## Criterios de aceptación

- [ ] Vista previa de apps instaladas en las 8 variantes y en “Iconos originales de Odoo”.
- [ ] La vista previa representa los mismos estilos que aparecen en el launcher, carpetas y Mi Espacio.
- [ ] Guardar/cancelar/restaurar son transaccionales y muestran confirmación del cambio aplicado.
- [ ] Búsqueda e importación solo aceptan IDs conocidos y assets del catálogo local.
- [ ] Un paquete inválido no altera preferencias existentes y explica el motivo.
- [ ] Tema claro/oscuro, escritorio y móvil mantienen geometría y contraste comprobables.
- [ ] Las preferencias por usuario sobreviven a cerrar sesión, cambiar dispositivo y actualizar el módulo.
- [ ] Instalación/upgrade QA conserva overrides personalizados y no duplica asignaciones.
- [ ] Pruebas Hoot, ORM, contraste y revisión visual forman parte del pipeline de release.

## Fuera de alcance

- Subir imágenes arbitrarias desde el navegador.
- Cambiar dinámicamente iconos internos de módulos de terceros sin adaptadores declarativos.
- Afirmar compatibilidad con otra versión principal de Odoo antes de probarla.

## Plan sugerido

1. Wireframe y revisión de permisos del administrador.
2. API del catálogo y esquema de importación/exportación.
3. Vista de comparación con datos de la base activa.
4. Persistencia global/personal y recuperación de valores.
5. Pruebas de upgrade, seguridad SVG, accesibilidad, Hoot y revisión visual en claro/oscuro/móvil.
