# Suite Personal — módulos, roles y plan

Plan completo y auditoría de la Fase 0 (12/11/2026): matriz existente / reutilizable /
faltante / a corregir sobre `main` c34cd05. Este documento resume lo que ya está en el
repositorio y cómo operarlo.

## Módulos

| Módulo | Estado | Depende de | Qué hace |
| --- | --- | --- | --- |
| `DOLAN_hr_core` | Ola 1 | `hr`, `analytic` | Legajo (CUIL, número, ingreso), establecimientos, centro de costos con vigencia, Supervisor de Personal, vínculo usuario-empleado |
| `DOLAN_payroll_ar` | Existente, 20.0.1.2.0 | `DOLAN_hr_core`, `account`, `l10n_ar` | Sueldos y Jornales; grupos propios (1.1.0), recibos confirmados inmutables con rectificación (1.2.0) |
| `DOLAN_hr_leave` | Ola 2 | `hr_holidays`, `DOLAN_hr_core` | Licencias LCT, vacaciones por antigüedad y proporcionales, topes, cobertura |
| `DOLAN_hr_scheduling` | Ola 3 (app Turnos) | `resource`, `hr_holidays`, `DOLAN_hr_core` | Turnos, ciclos, cuadrillas, cronogramas versionados |
| `DOLAN_hr_attendance` | Ola 4 | `hr_attendance`, scheduling | Relojes, eventos inmutables, conciliación, incidencias, correcciones (Turnos > Presentismo) |
| `DOLAN_hr_overtime` | Ola 4 | attendance, leave | Horas extra autorizadas, períodos de novedades (Turnos > Novedades) |
| `DOLAN_hr_payroll_bridge` | Ola 5 (auto) | overtime, `DOLAN_payroll_ar` | Novedades cerradas hacia recibos, una sola vez |
| `DOLAN_hr_portal` | Ola 6 | operativos | Mi legajo en el portal: turnos, saldos, pedidos, justificaciones, cambios de turno |
| `DOLAN_hr_portal_payroll` | Ola 6 (auto) | portal, `DOLAN_payroll_ar` | Recibos en el portal, PDF y firma |
| `DOLAN_hr_reports` | Ola 6 (app) | operativos | Tablero con acceso al origen, pivots y gráficos |
| `DOLAN_hr_documents` | Ola 7 | core | Legajo digital con vencimientos y conformidad |
| `DOLAN_hr_talent` | Ola 7 (app Gestión RRHH) | core, `hr_skills`, `hr_recruitment` | Capacitación, desempeño, selección |
| `DOLAN_personal_operativo` | Paquete | todos los operativos | Personal sin nómina |
| `DOLAN_personal` | Paquete | operativo, Sueldos, puente, portal de recibos, documentos, talento | Personal completo |

Cada módulo operativo nuevo se agrega a las dependencias de `DOLAN_personal_operativo`;
`bootstrap.sh --update` instala las dependencias nuevas de un paquete ya instalado.

## Roles

| Rol | Grupo | Ve sueldos |
| --- | --- | --- |
| Empleado | `base.group_user` | Solo sus recibos confirmados |
| Supervisor | `DOLAN_hr_core.group_dolan_hr_supervisor` | No |
| RRHH operativo | `hr.group_hr_user` (implica Supervisor) | No |
| Liquidación | `DOLAN_payroll_ar.group_dolan_payroll_user` (implica RRHH operativo) | Sí |
| Responsable de sueldos | `DOLAN_payroll_ar.group_dolan_payroll_manager` | Sí, y configura convenios y parámetros |
| Responsable RRHH | `hr.group_hr_manager` | No, salvo que tenga además un grupo de Sueldos |
| Administrador técnico | `base.group_system` | No por sí mismo |

Al actualizar `DOLAN_payroll_ar` a 20.0.1.1.0, quien era Oficial de Empleados recibe
Liquidación y quien era Administrador de Empleados recibe Responsable de sueldos, para
que nadie pierda acceso. Revisar y quitar esos grupos a quien no liquida sueldos.

## Legajo

- `hr.employee.dolan_cuil`, `dolan_file_number` y `dolan_seniority_date` viven en
  `DOLAN_hr_core` (antes en Sueldos, mismo nombre de campo).
- CUIL y legajo son únicos por compañía entre empleados activos. Se valida solo al
  crear o editar, así una base con duplicados históricos se actualiza igual.
- Sector = `department_id`, puesto = `job_id`, supervisor = `parent_id`, todos estándar y
  versionados en `hr.version`. Establecimiento y centro de costos se versionan igual.
- Usuarios > Vincular empleado: si hay fichas sin usuario que coinciden por correo, CUIL
  o nombre, obliga a vincular una en lugar de crear otra.
- `res.users.dolan_employee_or_guide()` devuelve el empleado del usuario o una acción de
  guía; los módulos siguientes la usan en vez de fallar con un error de acceso.

## Escritorio

`DOLAN_theme` siembra la carpeta Personal en escritorios nuevos. En uno ya armado,
Configuración de pantalla > Agregar carpeta Personal la crea o la completa, sin tocar el
resto. La carpeta solo muestra apps instaladas que el usuario puede abrir: agrupar no
da permisos.

## Flujo de presentismo a recibo

1. Turnos > Cronogramas: generar y publicar.
2. Asistencias > Relojes: importar CSV (o API). Los eventos quedan inmutables.
3. Turnos > Presentismo > Incidencias: conciliar (cron diario), justificar y aprobar.
4. Turnos > Novedades > Horas extra: aprobar con autorización previa o nota.
5. Turnos > Novedades > Períodos: recolectar y cerrar el mes.
6. Sueldos > Liquidación: Simular y luego Importar novedades; confirmar recibos.

Un recibo confirmado no se edita: Rectificar. Una novedad cerrada que cambia genera
una rectificación por diferencia en el período siguiente.
