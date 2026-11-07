package tui

import (
	"context"
	"fmt"
	"os"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/engine"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/jobs"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/packages"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/platform"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/updates"
)

type ScreenID string

const (
	ScreenHome            ScreenID = "7.1_home"
	ScreenChooseTarget    ScreenID = "7.2_target"
	ScreenLXCConfig       ScreenID = "7.3_lxc"
	ScreenSelectPackages  ScreenID = "7.4_packages"
	ScreenCompanyAndDemo  ScreenID = "7.5_company_demo"
	ScreenConfirmDeploy   ScreenID = "7.6_confirm"
	ScreenInstallProgress ScreenID = "7.7_install_progress"
	ScreenManageInstall   ScreenID = "7.8_manage"
	ScreenManagePackages  ScreenID = "7.9_manage_packages"
	ScreenCreateBackup    ScreenID = "7.10_create_backup"
	ScreenBackupProgress  ScreenID = "7.11_backup_progress"
	ScreenRestoreBackup   ScreenID = "7.12_restore"
	ScreenMigration       ScreenID = "7.13_migration"
	ScreenUpdates         ScreenID = "7.14_updates"
	ScreenConfiguration   ScreenID = "7.15_config"
	ScreenDiagnostics     ScreenID = "7.16_diagnostics"
)

type ManagedItem struct {
	ID         string
	VMID       int
	Name       string
	Profile    string
	DemoData   bool
	DemoMode   string
	Active     bool
	Deployment string
	Path       string
}

type ManagerModel struct {
	Screen          ScreenID
	History         []ScreenID
	Width           int
	Height          int
	Palette         ThemePalette
	Host            platform.HostEnvironment
	Installations   []ManagedItem
	SelectedInstall int
	Cursor          int
	Config          core.Config
	ActiveJobs      []jobs.Job
	BackupFile      string
	BackupDest      string
	BackupType      string
	IncludeFS       bool
	IncludeManifest bool
	VerifyBackup    bool
	EncryptBackup   bool
	UpdateCheck     updates.UpdateReport
	StatusMessage   string
	Quitting        bool
	StartWizard     bool
}

func NewManagerModel(ctx context.Context, root, repoRoot string) ManagerModel {
	cfg := core.NewConfig()
	if root != "" {
		cfg.ProjectRoot = root
	}
	cfg.Normalize()

	host := platform.DetectHostEnvironment()
	var items []ManagedItem

	if deps, err := engine.Discover(cfg.ProjectRoot); err == nil {
		for _, d := range deps {
			prof := "Comercio"
			if d.Managed && d.Manifest.Profile != "" {
				prof = core.ProfileDisplayName(core.Profile(d.Manifest.Profile))
			}
			st := engine.GetStatus(ctx, d)
			active := len(st.Containers) > 0 && st.Error == ""
			name := d.Name
			if d.Managed && d.Manifest.Company != "" {
				name = d.Manifest.Company
			}
			items = append(items, ManagedItem{
				ID:         d.Name,
				VMID:       d.Manifest.VMID,
				Name:       name,
				Profile:    prof,
				DemoData:   d.Manifest.DemoData,
				DemoMode:   d.Manifest.DemoMode,
				Active:     active,
				Deployment: d.Manifest.Deployment,
				Path:       d.Path,
			})
		}
	}

	if lxcs, err := platform.DiscoverProxmoxLXC(ctx); err == nil {
		for _, c := range lxcs {
			if !c.IsDolan {
				continue
			}
			prof := c.Profile
			if prof == "" {
				prof = "Comercio"
			}
			items = append(items, ManagedItem{
				ID:         fmt.Sprint(c.VMID),
				VMID:       c.VMID,
				Name:       c.Name,
				Profile:    prof,
				DemoData:   c.DemoData,
				DemoMode:   c.DemoMode,
				Active:     c.Status == "running",
				Deployment: "proxmox-lxc",
			})
		}
	}

	store := jobs.NewStore("")
	activeJobs, _ := store.ActiveJobs()

	return ManagerModel{
		Screen:          ScreenHome,
		Width:           100,
		Height:          30,
		Palette:         ActivePalette(),
		Host:            host,
		Installations:   items,
		Config:          cfg,
		ActiveJobs:      activeJobs,
		BackupFile:      "/mnt/backups/frigorifico.dolanbak",
		BackupDest:      "/mnt/backups/dolan/",
		BackupType:      "full",
		IncludeFS:       true,
		IncludeManifest: true,
		VerifyBackup:    true,
		EncryptBackup:   true,
		UpdateCheck:     updates.Check(repoRoot, "2.0.0", "20.0.1"),
	}
}

func RunManagerTUI(ctx context.Context, root, repoRoot string) error {
	if !isTerminal() {
		return fmt.Errorf("la TUI interactiva requiere una terminal TTY; usá subcomandos CLI o `--json`")
	}
	m := NewManagerModel(ctx, root, repoRoot)
	p := tea.NewProgram(m)
	final, err := p.Run()
	if err != nil {
		return err
	}
	res := final.(ManagerModel)
	if res.StartWizard {
		avail := packages.AllCatalogIDs()
		cfg, err := RunWizard(res.Config, avail)
		if err != nil {
			return err
		}
		return RunInstall(ctx, cfg, engine.Runner{RepoRoot: repoRoot})
	}
	return nil
}

func (m ManagerModel) Init() tea.Cmd { return nil }

func (m *ManagerModel) navigate(to ScreenID) {
	m.History = append(m.History, m.Screen)
	m.Screen = to
	m.Cursor = 0
}

func (m *ManagerModel) back() {
	if len(m.History) == 0 {
		m.Screen = ScreenHome
		m.Cursor = 0
		return
	}
	last := m.History[len(m.History)-1]
	m.History = m.History[:len(m.History)-1]
	m.Screen = last
	m.Cursor = 0
}

func (m ManagerModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.Width, m.Height = msg.Width, msg.Height
		return m, nil
	case tea.KeyPressMsg:
		key := msg.String()
		switch key {
		case "ctrl+c", "q", "Q":
			m.Quitting = true
			return m, tea.Quit
		case "esc":
			if m.Screen == ScreenHome {
				m.Quitting = true
				return m, tea.Quit
			}
			m.back()
			return m, nil
		case "up", "k":
			if m.Cursor > 0 {
				m.Cursor--
			}
			return m, nil
		case "down", "j", "tab":
			m.Cursor++
			return m, nil
		case "enter":
			return m.handleEnter()
		}
	}
	return m, nil
}

func (m ManagerModel) handleEnter() (tea.Model, tea.Cmd) {
	switch m.Screen {
	case ScreenHome:
		switch m.Cursor % 7 {
		case 0:
			m.navigate(ScreenChooseTarget)
		case 1:
			m.navigate(ScreenManageInstall)
		case 2:
			m.navigate(ScreenRestoreBackup)
		case 3:
			m.navigate(ScreenCreateBackup)
		case 4:
			m.navigate(ScreenUpdates)
		case 5:
			m.navigate(ScreenDiagnostics)
		case 6:
			m.navigate(ScreenConfiguration)
		}
	case ScreenChooseTarget:
		switch m.Cursor % 5 {
		case 0:
			m.Config.Target = core.TargetProxmoxLXC
			m.navigate(ScreenLXCConfig)
		case 1:
			m.Config.Target = core.TargetDocker
			m.navigate(ScreenSelectPackages)
		case 2:
			m.Config.Target = core.TargetLinuxNative
			m.navigate(ScreenSelectPackages)
		case 3:
			m.Config.Target = core.TargetWindows
			m.navigate(ScreenSelectPackages)
		case 4:
			m.navigate(ScreenRestoreBackup)
		}
	case ScreenLXCConfig:
		m.navigate(ScreenSelectPackages)
	case ScreenSelectPackages:
		profiles := []core.Profile{core.ProfileBasic, core.ProfileServices, core.ProfileCommerce, core.ProfileComplete, core.ProfileCustom}
		m.Config.Profile = profiles[m.Cursor%len(profiles)]
		m.navigate(ScreenCompanyAndDemo)
	case ScreenCompanyAndDemo:
		modes := []core.DemoMode{core.DemoNone, core.DemoOdoo, core.DemoDolan}
		m.Config.DemoMode = modes[m.Cursor%len(modes)]
		m.Config.DemoData = m.Config.DemoMode != core.DemoNone
		m.navigate(ScreenConfirmDeploy)
	case ScreenConfirmDeploy:
		m.StartWizard = true
		return m, tea.Quit
	case ScreenManageInstall:
		switch m.Cursor % 7 {
		case 0:
			m.navigate(ScreenManagePackages)
		case 1:
			m.navigate(ScreenUpdates)
		case 2:
			m.navigate(ScreenCreateBackup)
		case 3:
			m.navigate(ScreenRestoreBackup)
		case 4:
			m.navigate(ScreenConfiguration)
		case 5:
			m.navigate(ScreenDiagnostics)
		case 6:
			m.navigate(ScreenDiagnostics)
		}
	case ScreenCreateBackup:
		m.navigate(ScreenBackupProgress)
	case ScreenRestoreBackup:
		m.navigate(ScreenMigration)
	default:
		m.back()
	}
	return m, nil
}

func (m ManagerModel) View() tea.View {
	content := RenderScreen(m)
	v := tea.NewView(content)
	v.AltScreen = true
	return v
}

// RenderScreen renders any of the 16 mandatory reference screens (7.1 to 7.16),
// adapting to 120x35, 100x30, 80x24, compact terminals, no-color, and ASCII fallback.
func RenderScreen(m ManagerModel) string {
	p := m.Palette
	if m.Width > 0 && m.Width < 50 {
		return "DOLAN MANAGER v2.0 (Modo compacto: ampliá a 80x24)\n[Enter] Continuar  [Esc] Volver  [Q] Salir"
	}

	diamond := "◆"
	bulletOn := "●"
	bulletOff := "○"
	bulletRun := "◉"
	checkMark := "✓"
	radioOn := "(●)"
	radioOff := "( )"
	barFull := "█"
	barEmpty := "░"
	arrowDown := "↓"
	infoGlyph := "ℹ"

	if p.ASCIIOnly {
		diamond = "*"
		bulletOn = "*"
		bulletOff = "o"
		bulletRun = "@"
		checkMark = "[OK]"
		radioOn = "(*)"
		radioOff = "( )"
		barFull = "#"
		barEmpty = "-"
		arrowDown = "v"
		infoGlyph = "[i]"
	}

	var headerTitle, subtitle, footer string
	var body []string

	footer = "↑↓ Mover    ENTER Seleccionar    / Buscar    Q Salir"
	if p.ASCIIOnly {
		footer = "Up/Down Mover    ENTER Seleccionar    / Buscar    Q Salir"
	}

	switch m.Screen {
	case ScreenHome:
		headerTitle = fmt.Sprintf("%s DOLAN MANAGER                                    v2.0", diamond)
		subtitle = "Deployment & Lifecycle Management"
		body = append(body, fmt.Sprintf("ENTORNO: %s", m.Host.HeaderSummary()))
		body = append(body, "")
		if len(m.ActiveJobs) > 0 {
			body = append(body, fmt.Sprintf("! Tarea activa en segundo plano (reconexión SSH lista): %s (%d%%)", m.ActiveJobs[0].Title, m.ActiveJobs[0].OverallPercent))
			body = append(body, "")
		}
		body = append(body, "INSTALACIONES")
		if len(m.Installations) == 0 {
			body = append(body, fmt.Sprintf("  %s Sin instalaciones detectadas (creá una nueva o restaurá desde archivo)", bulletOff))
		} else {
			for _, inst := range m.Installations {
				glyph := bulletOff
				stateTxt := "Detenido"
				if inst.Active {
					glyph = bulletOn
					stateTxt = "Activo"
				}
				profLabel := inst.Profile
				if inst.DemoData || (inst.DemoMode != "" && inst.DemoMode != "none") {
					profLabel += " DEMO"
				}
				idLabel := inst.ID
				if inst.VMID > 0 {
					idLabel = fmt.Sprint(inst.VMID)
				}
				body = append(body, fmt.Sprintf("  %s %-4s %-16s %-14s %s", glyph, idLabel, inst.Name, profLabel, stateTxt))
			}
		}
		body = append(body, "")
		menu := []string{
			"Nueva instalación",
			"Administrar instalación",
			"Restaurar desde backup",
			"Backups",
			"Actualizaciones",
			"Diagnóstico",
			"Configuración",
		}
		for i, item := range menu {
			prefix := "   "
			if m.Cursor%len(menu) == i {
				prefix = " > "
			}
			body = append(body, prefix+item)
		}

	case ScreenChooseTarget:
		headerTitle = fmt.Sprintf("%s DOLAN / Nueva instalación", diamond)
		body = append(body, "¿Dónde querés instalar DOLAN?", "")
		targets := []string{
			"Proxmox LXC",
			"Docker",
			"Linux nativo",
			"Windows",
			"Restaurar instalación existente",
		}
		for i, t := range targets {
			prefix := "   "
			if m.Cursor%len(targets) == i {
				prefix = " > "
			}
			body = append(body, prefix+t)
		}
		body = append(body, "", fmt.Sprintf("Entorno detectado: %s", m.Host.DisplayName))
		footer = "ENTER Continuar                        ESC Volver"

	case ScreenLXCConfig:
		headerTitle = fmt.Sprintf("%s DOLAN / Proxmox LXC                  Paso 2 de 6", diamond)
		lxc := m.Config.LXC
		if lxc.VMID == 0 {
			lxc = core.DefaultLXCConfig()
		}
		body = append(body,
			fmt.Sprintf("Nombre          [ %-29s ]", lxc.Name),
			fmt.Sprintf("VMID            [ %-29d ]", lxc.VMID),
			fmt.Sprintf("Template        [ %-29s ]", lxc.Template),
			fmt.Sprintf("CPU             [ %-29d ]", lxc.CPU),
			fmt.Sprintf("RAM             [ %-29s ]", fmt.Sprintf("%d MB", lxc.RAMMB)),
			fmt.Sprintf("Disco           [ %-29s ]", fmt.Sprintf("%d GB", lxc.DiskGB)),
			fmt.Sprintf("Storage         [ %-29s ]", lxc.Storage),
			fmt.Sprintf("Bridge          [ %-29s ]", lxc.Bridge),
			fmt.Sprintf("VLAN            [ %-29s ]", lxc.VLAN),
			fmt.Sprintf("IP              [ %-29s ]", lxc.IP),
			fmt.Sprintf("DNS             [ %-29s ]", lxc.DNS),
			fmt.Sprintf("[%s] Iniciar al arrancar", checkMark),
			fmt.Sprintf("[%s] Habilitar backups Proxmox", checkMark),
			"Estado: configuración pendiente de validar",
		)
		footer = "TAB Siguiente campo   ENTER Continuar   ESC Volver"

	case ScreenSelectPackages:
		headerTitle = fmt.Sprintf("%s DOLAN / Paquetes                     Paso 3 de 6", diamond)
		body = append(body, "Seleccioná un perfil inicial")
		profiles := []struct {
			id    core.Profile
			label string
		}{
			{core.ProfileBasic, "Básico"},
			{core.ProfileServices, "Servicios"},
			{core.ProfileCommerce, "Comercio"},
			{core.ProfileComplete, "Completo"},
			{core.ProfileCustom, "Personalizado"},
		}
		sel := m.Cursor % len(profiles)
		for i, pr := range profiles {
			r := radioOff
			if i == sel {
				r = radioOn
			}
			body = append(body, fmt.Sprintf("  %s %s", r, pr.label))
		}
		info := core.FindProfileInfo(profiles[sel].id)
		body = append(body, "", strings.ToUpper(info.Title))
		for i := 0; i < len(info.FeatureBullets); i += 3 {
			end := i + 3
			if end > len(info.FeatureBullets) {
				end = len(info.FeatureBullets)
			}
			var row []string
			for _, b := range info.FeatureBullets[i:end] {
				row = append(row, fmt.Sprintf("%s %-12s", checkMark, b))
			}
			body = append(body, "  "+strings.Join(row, " "))
		}
		body = append(body, "", "Dependencias: se resolverán automáticamente", "[ Ver módulos ]  [ Personalizar ]  [ Continuar ]")
		footer = "↑↓ Elegir perfil   ENTER Continuar   ESC Volver"

	case ScreenCompanyAndDemo:
		headerTitle = fmt.Sprintf("%s DOLAN / Nueva empresa                Paso 4 de 6", diamond)
		comp := m.Config.Company
		if comp == "" {
			comp = "Empresa Demo SRL"
		}
		db := m.Config.InitDB
		if db == "" {
			db = "empresa_demo"
		}
		body = append(body,
			"EMPRESA",
			fmt.Sprintf("Nombre        [ %-30s ]", comp),
			fmt.Sprintf("Base de datos [ %-30s ]", db),
			fmt.Sprintf("País          [ %-30s ]", m.Config.Country),
			fmt.Sprintf("Idioma        [ %-30s ]", m.Config.Language),
			"",
			"DATOS DE DEMOSTRACIÓN",
			"¿Deseás instalar datos de ejemplo?",
			"",
		)
		opts := []string{
			"No, instalación limpia",
			"Sí, datos demo estándar de Odoo",
			"Sí, datos demo de DOLAN",
		}
		sel := m.Cursor % len(opts)
		for i, o := range opts {
			r := radioOff
			if i == sel {
				r = radioOn
			}
			body = append(body, fmt.Sprintf("  %s %s", r, o))
		}
		body = append(body,
			"",
			fmt.Sprintf("Perfil demo [ %s ▼ ]", m.Config.DemoProfile),
			fmt.Sprintf("%s Los datos demo son ficticios y no deben operar", infoGlyph),
			"  contra servicios externos reales.",
		)
		footer = "ESC Volver                          ENTER Continuar"

	case ScreenConfirmDeploy:
		headerTitle = fmt.Sprintf("%s DOLAN / Confirmar instalación         Paso 5 de 6", diamond)
		demoLabel := "No"
		if m.Config.DemoMode == core.DemoOdoo {
			demoLabel = "Sí (Estándar Odoo - DEMO)"
		} else if m.Config.DemoMode == core.DemoDolan {
			demoLabel = "Sí (DOLAN - DEMO)"
		}
		body = append(body,
			fmt.Sprintf("Cliente         %s", nonEmpty(m.Config.Company, "Frigorífico")),
			fmt.Sprintf("Entorno         %s %d", m.Config.Target, m.Config.LXC.VMID),
			"Sistema         Debian 13",
			fmt.Sprintf("Perfil          %s", core.ProfileDisplayName(m.Config.Profile)),
			fmt.Sprintf("Datos demo      %s", demoLabel),
			fmt.Sprintf("Recursos        %d CPU / %d GB / %d GB", m.Config.LXC.CPU, m.Config.LXC.RAMMB/1024, m.Config.LXC.DiskGB),
			"PostgreSQL      Local",
			fmt.Sprintf("%s VMID libre   %s Storage   %s Recursos   %s Dependencias", checkMark, checkMark, checkMark, checkMark),
			"[ Ver plan detallado ]",
			"[ Instalar ]                        [ Volver ]",
		)
		footer = "ENTER Confirmar e Instalar              ESC Volver"

	case ScreenInstallProgress:
		headerTitle = fmt.Sprintf("%s DOLAN / Instalando                   Paso 6 de 6", diamond)
		body = append(body,
			"Progreso general",
			renderBar(54, 32, barFull, barEmpty)+"  54%",
			fmt.Sprintf("  %s Crear contenedor LXC", checkMark),
			fmt.Sprintf("  %s Configurar Debian", checkMark),
			fmt.Sprintf("  %s Instalar PostgreSQL", checkMark),
			fmt.Sprintf("  %s Descargar Odoo Community", bulletRun),
			fmt.Sprintf("  %s Inicializar base de datos", bulletOff),
			fmt.Sprintf("  %s Instalar módulos DOLAN", bulletOff),
			fmt.Sprintf("  %s Cargar datos demo (si se eligieron)", bulletOff),
			fmt.Sprintf("  %s Verificación final", bulletOff),
			"",
			"Descargando repositorio...",
			renderBar(58, 24, barFull, barEmpty)+"  58%",
			"84.2 MB / 145 MB | 12.4 MB/s | ETA 00:05",
			"Último evento: recibiendo objetos...",
			"[L] Logs  [D] Detalles  [C] Cancelar de forma segura",
		)
		footer = "L Logs   D Detalles   C Cancelar de forma segura"

	case ScreenManageInstall:
		headerTitle = fmt.Sprintf("%s DOLAN / Frigorífico                    %s ACTIVO", diamond, bulletOn)
		body = append(body,
			"Entorno       Proxmox LXC 105",
			"Perfil        Comercio",
			"Odoo          Community 20",
			"DOLAN         20.0.1",
			"PostgreSQL    Operativo",
			"Datos demo    No",
			"CPU   "+renderBar(48, 10, barFull, barEmpty)+"  48%",
			"RAM   "+renderBar(62, 10, barFull, barEmpty)+"  62%",
			"Disco "+renderBar(37, 10, barFull, barEmpty)+"  37%",
		)
		opts := []string{
			"Administrar paquetes",
			"Actualizar instalación",
			"Crear backup",
			"Restaurar backup",
			"Configuración",
			"Servicios",
			"Logs y diagnóstico",
		}
		for i, o := range opts {
			prefix := "   "
			if m.Cursor%len(opts) == i {
				prefix = " > "
			}
			body = append(body, prefix+o)
		}
		footer = "↑↓ Mover   ENTER Seleccionar   ESC Volver"

	case ScreenManagePackages:
		headerTitle = fmt.Sprintf("%s DOLAN / Administrar paquetes", diamond)
		body = append(body,
			"Perfil actual: SERVICIOS",
			fmt.Sprintf("%s Básico   %s Servicios   %s Comercio", radioOff, radioOn, radioOff),
			fmt.Sprintf("%s Completo %s Personalizado", radioOff, radioOff),
			"MÓDULOS",
			fmt.Sprintf("[%s] CRM                  Instalado", checkMark),
			fmt.Sprintf("[%s] Ventas               Instalado", checkMark),
			fmt.Sprintf("[%s] Facturación          Instalado", checkMark),
			"[ ] Inventario           Disponible",
			"[ ] Punto de venta       Disponible",
			"[ ] Suscripciones        Disponible",
			"Cambios pendientes: +3 módulos",
			"[ Ver impacto ]  [ Aplicar cambios ]",
		)
		footer = "ENTER Ver impacto / Aplicar             ESC Volver"

	case ScreenCreateBackup:
		headerTitle = fmt.Sprintf("%s DOLAN / Crear backup", diamond)
		body = append(body,
			"Instalación     [ Frigorífico / LXC 105 ]",
			"Base de datos   [ Producción             ]",
			fmt.Sprintf("Tipo: %s Completo  %s Solo BD  %s Configuración", radioOn, radioOff, radioOff),
			fmt.Sprintf("Destino [ %-30s ]", m.BackupDest),
			fmt.Sprintf("[%s] Incluir filestore", checkMark),
			fmt.Sprintf("[%s] Incluir manifiesto", checkMark),
			fmt.Sprintf("[%s] Verificar integridad", checkMark),
			fmt.Sprintf("[%s] Cifrar backup", checkMark),
			"[ Crear backup ]                 [ Cancelar ]",
		)
		footer = "ENTER Crear backup                      ESC Cancelar"

	case ScreenBackupProgress:
		headerTitle = fmt.Sprintf("%s DOLAN / Backup en ejecución", diamond)
		body = append(body,
			"Frigorífico / Producción",
			renderBar(68, 30, barFull, barEmpty)+"  68%",
			fmt.Sprintf("  %s Validación inicial", checkMark),
			fmt.Sprintf("  %s Exportación PostgreSQL", checkMark),
			fmt.Sprintf("  %s Copia del filestore", bulletRun),
			fmt.Sprintf("  %s Empaquetado", bulletOff),
			fmt.Sprintf("  %s Verificación", bulletOff),
			"Procesados: 3.4 GB / 5.1 GB",
			"Velocidad: 82 MB/s",
			"Tiempo transcurrido: 01:24",
			"[L] Logs  [D] Detalles",
		)
		footer = "L Logs   D Detalles   ESC Volver (continúa en background)"

	case ScreenRestoreBackup:
		headerTitle = fmt.Sprintf("%s DOLAN / Restaurar instalación", diamond)
		body = append(body,
			fmt.Sprintf("Archivo [ %-34s ]", m.BackupFile),
			"Backup detectado",
			"Cliente        Frigorífico",
			"Odoo           Community 20",
			"DOLAN          20.0.1",
			"Perfil         Comercio",
			"Datos demo     No",
			"Tamaño         5.1 GB",
			"Destino",
			fmt.Sprintf("%s Nueva LXC Proxmox", radioOn),
			fmt.Sprintf("%s Docker  %s Linux nativo", radioOff, radioOff),
			fmt.Sprintf("%s Instalación existente", radioOff),
			"[ Analizar compatibilidad ]",
		)
		footer = "ENTER Analizar compatibilidad           ESC Volver"

	case ScreenMigration:
		headerTitle = fmt.Sprintf("%s DOLAN / Migrar instalación", diamond)
		body = append(body,
			"ORIGEN: Frigorífico / Docker / Servidor antiguo",
			"                      "+arrowDown,
			"DESTINO: Proxmox / LXC 110",
			fmt.Sprintf("%s Versiones compatibles", checkMark),
			fmt.Sprintf("%s Módulos disponibles", checkMark),
			fmt.Sprintf("%s Espacio suficiente", checkMark),
			"! Integraciones requieren revisión",
			"[ Iniciar migración ]  [ Ver detalles ]",
		)
		footer = "ENTER Iniciar migración                 ESC Volver"

	case ScreenUpdates:
		headerTitle = fmt.Sprintf("%s DOLAN / Actualizaciones", diamond)
		body = append(body, "COMPONENTE              ACTUAL        DISPONIBLE")
		for _, comp := range m.UpdateCheck.Components {
			body = append(body, fmt.Sprintf("%-23s %-13s %s", comp.Component, comp.Current, comp.Available))
		}
		opts := []string{
			"Actualizar Manager",
			"Actualizar módulos DOLAN",
			"Actualizar componentes compatibles",
			"Ver historial",
			"Comprobar actualizaciones",
		}
		for i, o := range opts {
			prefix := "   "
			if m.Cursor%len(opts) == i {
				prefix = " > "
			}
			body = append(body, prefix+o)
		}
		body = append(body, fmt.Sprintf("[%s] Crear backup antes de actualizar", checkMark))
		footer = "↑↓ Mover   ENTER Ejecutar   ESC Volver"

	case ScreenConfiguration:
		headerTitle = fmt.Sprintf("%s DOLAN / Configuración", diamond)
		opts := []string{
			"Parámetros Odoo",
			"PostgreSQL",
			"Red y puertos",
			"Proxy y dominio",
			"Correo saliente",
			"Integraciones",
			"Recursos y workers",
			"Backups programados",
			"Seguridad",
			"Variables de entorno",
		}
		for i, o := range opts {
			prefix := "   "
			if m.Cursor%len(opts) == i {
				prefix = " > "
			}
			body = append(body, prefix+o)
		}
		body = append(body, "[ Ver diferencias ] [ Aplicar cambios ]")
		footer = "↑↓ Mover   ENTER Editar   ESC Volver"

	case ScreenDiagnostics:
		headerTitle = fmt.Sprintf("%s DOLAN / Diagnóstico", diamond)
		body = append(body,
			fmt.Sprintf("%s Sistema operativo", checkMark),
			fmt.Sprintf("%s PostgreSQL", checkMark),
			fmt.Sprintf("%s Servicio Odoo", checkMark),
			fmt.Sprintf("%s Acceso HTTP", checkMark),
			fmt.Sprintf("%s Espacio disponible", checkMark),
			"! Backup pendiente",
			fmt.Sprintf("%s Integridad de módulos", checkMark),
			"CPU 18% | RAM 4.2/8 GB | Disco 32/80 GB",
			"[ Exportar diagnóstico ]",
		)
		footer = "ENTER Exportar diagnóstico              ESC Volver"
	}

	var out strings.Builder
	if p.NoColor {
		out.WriteString(headerTitle + "\n")
		if subtitle != "" {
			out.WriteString(subtitle + "\n")
		}
		out.WriteString(strings.Repeat("-", 60) + "\n")
		for _, line := range body {
			out.WriteString(line + "\n")
		}
		out.WriteString(strings.Repeat("-", 60) + "\n")
		out.WriteString(footer + "\n")
		return out.String()
	}

	hStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(p.Violet))
	subStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(p.Secondary))
	footStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(p.Blue))
	boxWidth := 64
	if m.Width >= 120 {
		boxWidth = 84
	} else if m.Width >= 100 {
		boxWidth = 72
	} else if m.Width > 0 && m.Width < 70 {
		boxWidth = m.Width - 4
	}

	out.WriteString(hStyle.Render(headerTitle) + "\n")
	if subtitle != "" {
		out.WriteString(subStyle.Render(subtitle) + "\n")
	}
	out.WriteString(subStyle.Render(strings.Repeat("─", max(20, boxWidth-4))) + "\n")
	for _, line := range body {
		out.WriteString(line + "\n")
	}
	out.WriteString(subStyle.Render(strings.Repeat("─", max(20, boxWidth-4))) + "\n")
	out.WriteString(footStyle.Render(footer))

	box := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color(p.Violet)).
		Padding(0, 1).
		Width(boxWidth)
	return box.Render(out.String())
}

func renderBar(percent, width int, fullChar, emptyChar string) string {
	if percent < 0 {
		percent = 0
	}
	if percent > 100 {
		percent = 100
	}
	filled := (percent * width) / 100
	return strings.Repeat(fullChar, filled) + strings.Repeat(emptyChar, width-filled)
}

func nonEmpty(v, fallback string) string {
	if strings.TrimSpace(v) == "" {
		return fallback
	}
	return v
}

func SetEnvForTest(k, v string) func() {
	old, existed := os.LookupEnv(k)
	_ = os.Setenv(k, v)
	return func() {
		if existed {
			_ = os.Setenv(k, old)
		} else {
			_ = os.Unsetenv(k)
		}
	}
}
