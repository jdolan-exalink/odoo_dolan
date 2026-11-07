# DOLAN UI 2.0 — sistema de diseño

## Principios

- Mantener la identidad DOLAN existente y evolucionarla por componentes.
- Usar nombres semánticos para que los componentes no tengan colores literales distintos por pantalla.
- Asegurar pares claro/oscuro con los mismos estados y estructura.
- Respetar la preferencia de movimiento reducido del sistema operativo.
- No imponer cambios de apariencia al flujo transaccional del POS sin habilitación separada.

## Implementación inicial

Los tokens están en `addons/DOLAN_theme/static/src/css/dolan_ui_tokens.css`, cargados antes de los estilos de componentes. Incluyen colores para superficie, texto, borde, primario, estados, tipografía, espacios, radios, elevación, movimiento e iconos. `body.o_dolan_dark_mode` sustituye los tokens de color y elevación para el modo oscuro.

El launcher usa los tokens de color, elevación, movimiento y foco. Una hoja por scopes aplica tokens a formularios, listas, kanban, menús e inputs comunes. Se excluyen deliberadamente POS transaccional y documentos impresos; la inspección visual de esas fronteras sigue en la matriz de QA.

## Tokens actuales

| Grupo | Tokens |
|---|---|
| Superficies y texto | `--dolan-color-canvas`, `--dolan-color-surface`, `--dolan-color-surface-raised`, `--dolan-color-text`, `--dolan-color-text-muted`, `--dolan-color-border` |
| Marca y estados | `--dolan-color-primary`, `--dolan-color-primary-hover`, `--dolan-color-secondary`, `--dolan-color-success`, `--dolan-color-warning`, `--dolan-color-danger`, `--dolan-color-info`, `--dolan-color-focus` |
| Texto | `--dolan-font-family`, `--dolan-font-size-xs` a `--dolan-font-size-xl` |
| Espaciado | `--dolan-space-1`, `--dolan-space-2`, `--dolan-space-3`, `--dolan-space-4`, `--dolan-space-6`, `--dolan-space-8` |
| Forma y elevación | `--dolan-radius-*`, `--dolan-border-width`, `--dolan-shadow-sm`, `--dolan-shadow-md`, `--dolan-elevation-overlay` |
| Movimiento | `--dolan-motion-fast`, `--dolan-motion-normal`, `--dolan-motion-slow`, `--dolan-ease-standard` |
| Iconos | `--dolan-icon-navigation`, `--dolan-icon-action`, `--dolan-icon-status`, `--dolan-icon-shortcut`, `--dolan-icon-launcher`, `--dolan-icon-folder-preview` |

## Decisiones y pendientes

- La paleta clara/oscura parte de los valores orientativos del PRD. Los colores de estado se asignan por separado para permitir revisar contraste componente a componente.
- `color-scheme` permite que controles nativos sigan el tema activo.
- `prefers-reduced-motion` reduce a cero las duraciones tokenizadas; cada animación nueva debe usar estos tokens.
- El tema automático según el sistema está disponible en `dolan.screen.preference`; el listener de `prefers-color-scheme` actualiza el launcher y el login.
- No se declara conformidad WCAG por definir colores: debe medirse el contraste de los componentes migrados y documentar excepciones.
- El acento existente `--dolan-primary` se conserva durante la migración. Los componentes nuevos usan `--dolan-color-primary`; su unificación visual completa queda para el QA de runtime.

## Regla de uso

Los estilos nuevos de DOLAN deben usar estos tokens en lugar de colores, radios, sombras o espacios literales. Al migrar un selector existente, revisar las capturas en tema claro y oscuro, móvil y escritorio, y las pantallas de documentos relacionadas.
