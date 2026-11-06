package tui

import "charm.land/lipgloss/v2"

var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#7C5C8A"))
	sectionStyle  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#20B8AA"))
	selectedStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("#FFFFFF")).Background(lipgloss.Color("#714B67")).Bold(true)
	dimStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("#8D99A8"))
	keyStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("#20B8AA")).Bold(true)
	warnStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("#E0A45B"))
	errorStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("#E36A72")).Bold(true)
	panelStyle    = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("#505564")).Padding(1, 2)
)
