package tui

import (
	"context"
	"fmt"
	"os"
	"strings"

	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
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
	lines         []string
	width, height int
	done          bool
	err           error
	canceled      bool
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
	return waitEvent(m.events)
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
		m.viewport.SetHeight(max(6, m.height-10))
		return m, nil
	case engine.Event:
		if msg.Line != "" {
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
		if msg.String() == "ctrl+c" && !m.done {
			m.canceled = true
			m.cancel()
			m.lines = append(m.lines, "Cancelando de forma controlada. Los datos persistentes se conservarán.")
			m.viewport.SetContentLines(m.lines)
			m.viewport.GotoBottom()
			return m, waitEvent(m.events)
		}
		if m.done && (msg.String() == "enter" || msg.String() == "esc" || msg.String() == "q") {
			return m, tea.Quit
		}
		var cmd tea.Cmd
		m.viewport, cmd = m.viewport.Update(msg)
		return m, cmd
	}
	return m, nil
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
	b.WriteString(m.viewport.View())
	b.WriteString("\n")
	if m.done {
		if m.err != nil {
			b.WriteString(errorStyle.Render("Falló el despliegue. Revisá el log privado indicado en el error."))
		} else {
			b.WriteString(sectionStyle.Render("Proceso completado; verificá salud con dolan-installer status."))
		}
		b.WriteString("  " + keyStyle.Render("Enter") + " salir")
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
