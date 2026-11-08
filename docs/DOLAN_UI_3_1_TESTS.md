# DOLAN UI 3.1 — plan de pruebas

## Automatizadas

- `DOLAN_theme.tests.test_screen_preferences`: política de preferencias y personalización.
- `DOLAN_theme.tests.test_workspace_multicompany`: compañías activas, contactos compartidos y modelos sin frontera.
- `DOLAN_discount_engine.tests.test_discount_engine`: preservación de campos nativos del POS.
- Validar Python, XML OWL, JavaScript y `git diff --check` antes de empaquetar.

## Matriz manual de aceptación

1. Probar cinco perfiles y ocho paletas en claro, oscuro y alto contraste.
2. Cambiar estilo Odoo/Fluent/Tabler y validar grilla, carpetas, Mi Espacio y accesos POS.
3. Probar tres tamaños, densidad, efecto suave/Glass y reducción de movimiento/transparencia.
4. Verificar preferencias personales tras cerrar sesión y entrar desde otro equipo.
5. Verificar A, B, C, A+B, A+C y A+B+C; KPI, POS, actividad, contactos compartidos y estados personales.
6. Cambiar empresas rápidamente y confirmar que la acción recargada no conserva datos obsoletos.
7. Verificar móvil, desktop, colores, truncamiento, foco/teclado y fallback sin blur.

No se declarará la matriz completa aprobada hasta ejecutar datos multicompañía controlados y QA visual en las variantes indicadas.
