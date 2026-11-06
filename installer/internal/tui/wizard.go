package tui

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"charm.land/bubbles/v2/textinput"
	tea "charm.land/bubbletea/v2"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"golang.org/x/term"
)

type field struct { key, label, help string; secret bool }

type wizardModel struct {
	cfg core.Config
	modules []string
	steps []field
	index int
	input textinput.Model
	profileIndex int
	responsibilityIndex int
	err string
	review bool
	confirmed bool
	canceled bool
	width, height int
	showPassword bool
}

var responsibilityOptions = []string{"Responsable Inscripto", "Monotributista", "Exento"}

func RunWizard(cfg core.Config, modules []string) (core.Config, error) {
	if !term.IsTerminal(int(os.Stdin.Fd())) || !term.IsTerminal(int(os.Stdout.Fd())) { return cfg, errors.New("no hay una terminal interactiva; usá `install --config archivo.json --non-interactive`") }
	cfg.Normalize()
	steps := []field{
		{"company", "Razón social", "Nombre legal tal como figura ante ARCA." , false},
		{"short", "Nombre corto", "Se usa para la carpeta y la base de datos.", false},
		{"cuit", "CUIT", "11 dígitos con verificador; se permiten guiones.", false},
		{"address", "Domicilio fiscal", "Domicilio de la empresa inicial.", false},
		{"city", "Localidad", "Ciudad o localidad fiscal.", false},
		{"responsibility", "Responsabilidad ARCA", "Seleccioná la condición fiscal de la empresa.", false},
		{"billing_pos", "Punto de venta de facturación", "Número de PV habilitado en ARCA.", false},
		{"pos_pos", "Punto de venta de POS", "PV para POS (puede coincidir si así lo configurás en ARCA).", false},
		{"admin_email", "Correo del administrador", "Este será el usuario de acceso inicial a Odoo.", false},
		{"admin_name", "Nombre del administrador", "Nombre visible en Odoo.", false},
		{"admin_password", "Contraseña inicial", "Se configura para la cuenta administradora; no se muestra ni se registra.", true},
		{"admin_password_confirm", "Confirmar contraseña", "Volvé a escribir la contraseña inicial.", true},
		{"master_password", "Contraseña maestra de Odoo", "Opcional: Enter genera una contraseña aleatoria privada.", true},
		{"port", "Puerto HTTP", "Puerto publicado para entrar a Odoo.", false},
		{"callback_port", "Puerto de callback OAuth", "Puerto loopback para el retorno de ChatGPT.", false},
	}
	if cfg.Profile == core.ProfileCustom { steps = append(steps, field{"modules", "Módulos custom", "Ingresá IDs separados por coma. Disponibles: " + strings.Join(modules, ", "), false}) }
	m := wizardModel{cfg: cfg, modules: modules, steps: steps, input: textinput.New(), index: -1, width: 80, height: 24}
	for i, profile := range core.ProfileCatalog { if profile.ID == cfg.Profile { m.profileIndex = i; break } }
	for i, option := range responsibilityOptions { if option == cfg.Responsibility { m.responsibilityIndex = i; break } }
	m.input.Prompt = "› "
	m.input.Placeholder = "Ingresá un valor"
	m.input.CharLimit = 256
	m.input.SetWidth(58)
	m.configureInput()
	p := tea.NewProgram(m)
	final, err := p.Run()
	if err != nil { return cfg, err }
	result := final.(wizardModel)
	if result.canceled { return cfg, errors.New("instalación cancelada antes de realizar cambios") }
	if !result.confirmed { return cfg, errors.New("no se confirmó la instalación") }
	result.cfg.Normalize()
	return result.cfg, nil
}

func (m wizardModel) Init() tea.Cmd { return m.input.Focus() }

func (m wizardModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.input.SetWidth(max(24, min(64, m.width-18)))
		return m, nil
	case tea.KeyPressMsg:
		switch msg.String() {
		case "ctrl+c", "esc":
			m.canceled = true
			return m, tea.Quit
		case "f1":
			m.err = "Teclado: ↑/↓ cambia opción, Enter confirma o avanza, Tab avanza, Shift+Tab vuelve, Ctrl+P muestra/oculta contraseña. Esc cancela antes de iniciar."
			return m, nil
		case "ctrl+p":
			m.showPassword = !m.showPassword
			m.configureInput()
			return m, nil
		case "tab", "enter":
			if m.review { m.confirmed = true; return m, tea.Quit }
			if m.index == -1 { m.index = 0; m.err = ""; m.configureInput(); return m, m.input.Focus() }
			if m.steps[m.index].key == "responsibility" { m.cfg.Responsibility = responsibilityOptions[m.responsibilityIndex] }
			if err := m.saveCurrent(); err != nil { m.err = err.Error(); return m, nil }
			m.err = ""
			m.index++
			if m.index >= len(m.steps) {
				m.cfg.Normalize()
				if err := m.cfg.Validate(true); err != nil { m.index = len(m.steps)-1; m.err = err.Error(); return m, nil }
				m.review = true
				return m, nil
			}
			m.configureInput()
			return m, m.input.Focus()
		case "shift+tab":
			if m.review { m.review = false; m.index = len(m.steps)-1; m.configureInput(); return m, m.input.Focus() }
			if m.index > 0 { m.index--; m.configureInput(); return m, m.input.Focus() }
			if m.index == 0 { m.index = -1; return m, nil }
			return m, nil
		case "up", "down":
			if m.review { return m, nil }
			if m.index == -1 {
				m.profileIndex = (m.profileIndex + len(core.ProfileCatalog) + map[string]int{"up": -1, "down": 1}[msg.String()]) % len(core.ProfileCatalog)
				m.cfg.Profile = core.ProfileCatalog[m.profileIndex].ID
				m.setStepsForProfile()
				return m, nil
			}
			if m.index >= 0 && m.index < len(m.steps) && m.steps[m.index].key == "responsibility" {
				m.responsibilityIndex = (m.responsibilityIndex + len(responsibilityOptions) + map[string]int{"up": -1, "down": 1}[msg.String()]) % len(responsibilityOptions)
				m.cfg.Responsibility = responsibilityOptions[m.responsibilityIndex]
				return m, nil
			}
		}
	}
	if !m.review && m.index >= 0 { var cmd tea.Cmd; m.input, cmd = m.input.Update(msg); return m, cmd }
	return m, nil
}

func (m wizardModel) View() tea.View {
	if m.width < 58 || m.height < 16 {
		return tea.NewView("DOLAN Installer 2.0\nTerminal pequeña: recomendado 58×16 o superior.\nAmpliá la terminal para continuar.\nEsc cancela")
	}
	var b strings.Builder
	b.WriteString(titleStyle.Render("DOLAN Installer 2.0"))
	b.WriteString("  ")
	b.WriteString(dimStyle.Render("Instalación local Linux · Odoo 20 CE"))
	b.WriteString("\n")
	if m.review {
		b.WriteString(sectionStyle.Render("Revisá el plan antes de modificar el servidor"))
		b.WriteString("\n\n")
		b.WriteString(fmt.Sprintf("Perfil:         %s\nEmpresa:        %s\nCUIT:           %s\nProyecto:       %s\nBase de datos:  %s\nAdministrador:  %s\nURL prevista:   http://<IP>:%d/web/login\n\n", m.cfg.Profile, m.cfg.Company, m.cfg.CUIT, m.cfg.DeploymentPath(), m.cfg.InitDB, m.cfg.AdminEmail, m.cfg.Port))
		b.WriteString(warnStyle.Render("Va a instalar paquetes del sistema, activar Docker, descargar módulos y contenedores, y crear una base nueva."))
		b.WriteString("\nLos datos persistentes no se eliminarán automáticamente.\n")
		b.WriteString("\n" + keyStyle.Render("Enter") + " confirma e inicia  " + keyStyle.Render("Shift+Tab") + " vuelve  " + keyStyle.Render("Esc") + " cancela")
		if m.err != "" { b.WriteString("\n" + errorStyle.Render(m.err)) }
		return tea.NewView(panelStyle.Width(m.width-6).Render(b.String()))
	}
	if m.index == -1 {
		b.WriteString(sectionStyle.Render("Elegí el perfil de módulos"))
		b.WriteString("\n\n")
		for i, profile := range core.ProfileCatalog {
			marker := "  "
			if i == m.profileIndex { marker = "› " }
			line := marker + profile.Title + " — " + profile.Summary
			if i == m.profileIndex { b.WriteString(selectedStyle.Render(line)) } else { b.WriteString(line) }
			b.WriteString("\n")
		}
		b.WriteString("\n" + keyStyle.Render("↑/↓") + " elegir  " + keyStyle.Render("Enter") + " continuar  " + keyStyle.Render("F1") + " ayuda")
		return tea.NewView(panelStyle.Width(m.width-6).Render(b.String()))
	}
	if m.index >= 0 && m.index < len(m.steps) && m.steps[m.index].key == "responsibility" {
		b.WriteString(sectionStyle.Render("Condición frente a ARCA"))
		for i, option := range responsibilityOptions { mark := "  "; if i == m.responsibilityIndex { mark = "› " }; b.WriteString("\n"+mark+option) }
		b.WriteString("\n\n↑/↓ elegir · Enter continuar · Shift+Tab volver")
		return tea.NewView(panelStyle.Width(m.width-6).Render(b.String()))
	}
	if m.index > len(m.steps)-1 { m.index = len(m.steps)-1 }
	current := m.steps[m.index]
	b.WriteString(sectionStyle.Render(fmt.Sprintf("Paso %02d de %02d · %s", m.index+1, len(m.steps), current.label)))
	b.WriteString("\n\n" + current.help + "\n\n")
	b.WriteString(m.input.View())
	b.WriteString("\n\n" + dimStyle.Render("↑/↓ opciones  ·  Enter/Tab continuar  ·  Shift+Tab volver  ·  F1 ayuda  ·  Esc salir"))
	if current.secret { b.WriteString("\n" + dimStyle.Render("Ctrl+P muestra u oculta el campo actual")) }
	if m.err != "" { b.WriteString("\n\n" + errorStyle.Render(m.err)) }
	return tea.NewView(panelStyle.Width(m.width-6).Render(b.String()))
}

func (m *wizardModel) configureInput() {
	if m.index < 0 || m.index >= len(m.steps) { return }
	f := m.steps[m.index]
	m.input = textinput.New()
	m.input.Prompt = "› "
	m.input.SetWidth(max(24, min(64, m.width-18)))
	if f.secret { m.input.EchoMode = textinput.EchoPassword; m.input.EchoCharacter = '•'; if m.showPassword { m.input.EchoMode = textinput.EchoNormal } }
	m.input.SetValue(m.getField(f.key))
	if f.key == "company_short" && m.cfg.CompanyShort != "" { m.input.SetValue(m.cfg.CompanyShort) }
	_ = m.input.Focus()
}

func (m *wizardModel) setStepsForProfile() { if m.cfg.Profile == core.ProfileCustom { if len(m.steps) == 15 { m.steps = append(m.steps, field{"modules", "Módulos custom", "Ingresá IDs separados por coma. Disponibles: " + strings.Join(m.modules, ", "), false}) } } else if len(m.steps) == 16 { m.steps = m.steps[:15] } }

func (m wizardModel) getField(key string) string {
	switch key {
	case "company": return m.cfg.Company
	case "short": return m.cfg.CompanyShort
	case "cuit": return m.cfg.CUIT
	case "address": return m.cfg.Address
	case "city": return m.cfg.City
	case "responsibility": return m.cfg.Responsibility
	case "billing_pos": return fmt.Sprint(m.cfg.BillingPOS)
	case "pos_pos": return fmt.Sprint(m.cfg.POSPOS)
	case "admin_email": return m.cfg.AdminEmail
	case "admin_name": return m.cfg.AdminName
	case "admin_password": return m.cfg.AdminPassword
	case "admin_password_confirm": return ""
	case "master_password": return m.cfg.MasterPassword
	case "port": return fmt.Sprint(m.cfg.Port)
	case "callback_port": return fmt.Sprint(m.cfg.CallbackPort)
	case "modules": return strings.Join(m.cfg.Modules, ",")
	}
	return ""
}

func (m *wizardModel) saveCurrent() error {
	f := m.steps[m.index]
	v := strings.TrimSpace(m.input.Value())
	switch f.key {
	case "company": m.cfg.Company = v
	case "short": m.cfg.CompanyShort = core.Slugify(v); if m.cfg.CompanyShort == "" { return errors.New("el nombre corto quedó vacío") }
	case "cuit": m.cfg.CUIT = v
	case "address": m.cfg.Address = v
	case "city": m.cfg.City = v
	case "responsibility": m.cfg.Responsibility = responsibilityOptions[m.responsibilityIndex]
	case "billing_pos": n, err := parsePositive(v); if err != nil { return err }; m.cfg.BillingPOS = n
	case "pos_pos": n, err := parsePositive(v); if err != nil { return err }; m.cfg.POSPOS = n
	case "admin_email": m.cfg.AdminEmail = v
	case "admin_name": m.cfg.AdminName = v
	case "admin_password": if len(v) < 10 { return errors.New("usá al menos 10 caracteres") }; m.cfg.AdminPassword = v
	case "admin_password_confirm": if v != m.cfg.AdminPassword { return errors.New("las contraseñas no coinciden") }
	case "master_password": m.cfg.MasterPassword = v
	case "port": n, err := parsePositive(v); if err != nil { return err }; m.cfg.Port = n
	case "callback_port": n, err := parsePositive(v); if err != nil { return err }; m.cfg.CallbackPort = n
	case "modules": m.cfg.Modules = splitCSV(v); if len(m.cfg.Modules) == 0 { return errors.New("elegí al menos un módulo para el perfil custom") }
	}
	if f.key == "company" && m.cfg.CompanyShort == "" { m.cfg.CompanyShort = core.Slugify(v) }
	if f.key == "company" && m.cfg.CompanyShort != "" { /* suggested short name appears on its step */ }
	if f.key == "modules" { for _, module := range m.cfg.Modules { if !contains(m.modules, module) { return fmt.Errorf("módulo no disponible en el repositorio: %s", module) } } }
	if f.key == "short" { m.cfg.ProjectName = m.cfg.CompanyShort; m.cfg.InitDB = "odoo_" + m.cfg.CompanyShort }
	return nil
}

func parsePositive(v string) (int, error) { var n int; if _, err := fmt.Sscanf(v, "%d", &n); err != nil || n < 1 { return 0, errors.New("ingresá un número entero positivo") }; return n, nil }
func splitCSV(v string) []string { var out []string; for _, item := range strings.Split(v, ",") { item = strings.TrimSpace(item); if item != "" { out = append(out, item) } }; return out }
func contains(items []string, value string) bool { for _, item := range items { if item == value { return true } }; return false }
