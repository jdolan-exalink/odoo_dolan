package tui

import (
	"context"
	"fmt"
	"os"
	"strings"

	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/engine"
	"golang.org/x/term"
)

type installModel struct {
	ctx           context.Context
	cancel        context.CancelFunc
	runner        engine.Runner
	cfg           core.Config
	viewport      viewport.Model
	spinner       spinner.Model
	stage         string
	lines         []string
	width, height int
	done          bool
	err           error
	canceled      bool
	confirmExit   bool
	events        chan engine.Event
}

func RunInstall(ctx context.Context, cfg core.Config, runner engine.Runner) error {
	if !isTerminal() {
		return runner.Install(ctx, cfg, func(e engine.Event) {
			if e.Line != "" {
				fmt.Println(e.Line)
			}
		})
	}
	ctx, cancel := context.WithCancel(ctx)
	m := installModel{ctx: ctx, cancel: cancel, runner: runner, cfg: cfg, width: 80, height: 24, events: make(chan engine.Event, 64)}
	m.spinner = spinner.New()
	m.spinner.Spinner = spinner.Dot
	m.spinner.Style = lipgloss.NewStyle().Foreground(lipgloss.Color("#20B8AA"))
	m.stage = "Preparando el servidor"
	m.viewport = viewport.New(viewport.WithWidth(74), viewport.WithHeight(14))
	m.viewport.SoftWrap = true
	m.viewport.MouseWheelEnabled = true
	p := tea.NewProgram(m)
	final, err := p.Run()
	cancel()
	if err != nil {
		return err
	}
	result := final.(installModel)
	if result.err != nil {
		return result.err
	}
	if result.canceled {
		return context.Canceled
	}
	return nil
}

func (m installModel) Init() tea.Cmd {
	go func() {
		err := m.runner.Install(m.ctx, m.cfg, func(e engine.Event) { m.events <- e })
		m.events <- engine.Event{Done: true, Err: err}
		close(m.events)
	}()
	return tea.Batch(waitEvent(m.events), func() tea.Msg { return m.spinner.Tick() })
}

func waitEvent(ch <-chan engine.Event) tea.Cmd {
	return func() tea.Msg {
		e, ok := <-ch
		if !ok {
			return engine.Event{Done: true}
		}
		return e
	}
}

func (m installModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.viewport.SetWidth(max(24, m.width-8))
		m.viewport.SetHeight(max(4, m.height-12))
		return m, nil
	case spinner.TickMsg:
		if m.done {
			return m, nil
		}
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	case engine.Event:
		if msg.Line != "" {
			if stage := stageForLog(msg.Line); stage != "" {
				m.stage = stage
			}
			m.lines = append(m.lines, msg.Line)
			if len(m.lines) > 3000 {
				m.lines = m.lines[len(m.lines)-3000:]
			}
			m.viewport.SetContentLines(m.lines)
			m.viewport.GotoBottom()
		}
		if msg.Done {
			m.done = true
			m.err = msg.Err
			if m.err != nil {
				m.lines = append(m.lines, "ERROR: "+m.err.Error())
				m.viewport.SetContentLines(m.lines)
				m.viewport.GotoBottom()
			}
			return m, nil
		}
		return m, waitEvent(m.events)
	case tea.KeyPressMsg:
		if m.done && m.confirmExit {
			switch msg.String() {
			case "enter":
				return m, tea.Quit
			case "esc":
				m.confirmExit = false
			}
			return m, nil
		}
		if m.done && (msg.String() == "esc" || msg.String() == "q") {
			m.confirmExit = true
			return m, nil
		}
		if msg.String() == "ctrl+c" && !m.done {
			m.canceled = true
			m.cancel()
			m.lines = append(m.lines, "Cancelando de forma controlada. Los datos persistentes se conservarán.")
			m.viewport.SetContentLines(m.lines)
			m.viewport.GotoBottom()
			return m, waitEvent(m.events)
		}
		if m.done && msg.String() == "enter" {
			return m, tea.Quit
		}
		var cmd tea.Cmd
		m.viewport, cmd = m.viewport.Update(msg)
		return m, cmd
	}
	return m, nil
}

func stageForLog(line string) string {
	s := strings.ToLower(line)
	switch {
	case strings.Contains(s, "eliminando deployment"):
		return "Preparando una instalación limpia"
	case strings.Contains(s, "apt-get") || strings.Contains(s, "preparando los paquetes") || strings.Contains(s, "instalando dependencias"):
		return "Instalando dependencias del servidor"
	case strings.Contains(s, "descargando modulos") || strings.Contains(s, "copiando suite de modulos"):
		return "Descargando y preparando los módulos"
	case strings.Contains(s, "docker build") || strings.Contains(s, "building") || strings.Contains(s, "exporting") || strings.Contains(s, "construyendo y levantando contenedores") || strings.Contains(s, "descargando") && strings.Contains(s, "imagen"):
		return "Construyendo y descargando imágenes"
	case strings.Contains(s, "docker compose up") || strings.Contains(s, "creating") || strings.Contains(s, "starting") || strings.Contains(s, "started"):
		return "Iniciando los servicios de Odoo y PostgreSQL"
	case strings.Contains(s, "esperando") && (strings.Contains(s, "odoo") || strings.Contains(s, "servicio")) || strings.Contains(s, "health"):
		return "Esperando que Odoo esté listo"
	case strings.Contains(s, "inicializando db") || strings.Contains(s, "odoo -i") || strings.Contains(s, "initializing") || strings.Contains(s, "loading module") || strings.Contains(s, "cargando módulos") || strings.Contains(s, "modules loaded"):
		return "Creando la base de datos e instalando módulos"
	case strings.Contains(s, "configurando la empresa") || strings.Contains(s, "usuario inicial") || strings.Contains(s, "company_onboarding"):
		return "Configurando la empresa y el usuario administrador"
	case strings.Contains(s, "manifiesto guardado"):
		return "Guardando la configuración del despliegue"
	}
	return ""
}

func (m installModel) View() tea.View {
	if m.width < 45 || m.height < 12 {
		return tea.NewView("DOLAN Installer 2.0\nTerminal pequeña: recomendado 45×12 o superior.\nCtrl+C cancela de forma controlada.")
	}
	var b strings.Builder
	b.WriteString(titleStyle.Render("DOLAN Installer 2.0"))
	b.WriteString(" · ")
	b.WriteString(sectionStyle.Render("Despliegue en ejecución"))
	b.WriteString("\n")
	b.WriteString(dimStyle.Render(fmt.Sprintf("%s · %s · %s", m.cfg.Company, m.cfg.Profile, m.cfg.DeploymentPath())))
	b.WriteString("\n\n")
	if !m.done {
		b.WriteString(m.spinner.View())
		b.WriteString("  ")
		b.WriteString(sectionStyle.Render(m.stage))
		b.WriteString("\n\n")
	}
	b.WriteString(m.viewport.View())
	b.WriteString("\n")
	if m.done {
		if m.err != nil {
			b.WriteString(errorStyle.Render("Falló el despliegue. Revisá el log privado indicado en el error."))
		} else {
			b.WriteString(sectionStyle.Render("Proceso completado; verificá salud con dolan-installer status."))
		}
		if m.confirmExit {
			b.WriteString("  " + warnStyle.Render("¿Salir del instalador? ") + keyStyle.Render("Enter") + " confirmar · " + keyStyle.Render("Esc") + " volver")
		} else {
			b.WriteString("  " + keyStyle.Render("Enter") + " salir · " + keyStyle.Render("Esc") + " consultar antes de salir")
		}
	} else {
		b.WriteString(warnStyle.Render("Ctrl+C cancela el proceso; no elimina datos persistentes."))
	}
	v := tea.NewView(panelStyle.Width(m.width - 4).Render(b.String()))
	v.AltScreen = true
	if mouseCompatible() {
		v.MouseMode = tea.MouseModeCellMotion
	}
	return v
}

func isTerminal() bool {
	return os.Stdin != nil && os.Stdout != nil && term.IsTerminal(int(os.Stdin.Fd())) && term.IsTerminal(int(os.Stdout.Fd()))
}
func mouseCompatible() bool {
	t := strings.ToLower(os.Getenv("TERM"))
	return strings.Contains(t, "xterm") || strings.Contains(t, "screen") || strings.Contains(t, "tmux") || strings.Contains(t, "kitty") || strings.Contains(t, "wezterm") || strings.Contains(t, "alacritty")
}
