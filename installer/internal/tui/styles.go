package tui

import (
	"os"
	"strings"

	"charm.land/lipgloss/v2"
)

type ThemePalette struct {
	Background string
	Surface    string
	Violet     string
	Blue       string
	Green      string
	Yellow     string
	Red        string
	Text       string
	Secondary  string
	Border     string
	NoColor    bool
	ASCIIOnly  bool
}

var DarkPalette = ThemePalette{
	Background: "#10131B",
	Surface:    "#1B2130",
	Violet:     "#8B5CF6",
	Blue:       "#38BDF8",
	Green:      "#22C55E",
	Yellow:     "#F59E0B",
	Red:        "#EF4444",
	Text:       "#F1F5F9",
	Secondary:  "#94A3B8",
	Border:     "#334155",
}

var LightPalette = ThemePalette{
	Background: "#F8FAFC",
	Surface:    "#FFFFFF",
	Violet:     "#6D28D9",
	Blue:       "#0284C7",
	Green:      "#16A34A",
	Yellow:     "#D97706",
	Red:        "#DC2626",
	Text:       "#0F172A",
	Secondary:  "#475569",
	Border:     "#94A3B8",
}

func ActivePalette() ThemePalette {
	p := DarkPalette
	if strings.EqualFold(os.Getenv("DOLAN_THEME"), "light") {
		p = LightPalette
	}
	if os.Getenv("NO_COLOR") != "" || strings.EqualFold(os.Getenv("TERM"), "dumb") || strings.EqualFold(os.Getenv("DOLAN_NO_COLOR"), "1") {
		p.NoColor = true
	}
	if strings.EqualFold(os.Getenv("DOLAN_ASCII"), "1") || strings.EqualFold(os.Getenv("TERM"), "dumb") || strings.EqualFold(os.Getenv("TERM"), "linux") {
		p.ASCIIOnly = true
	}
	return p
}

var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(DarkPalette.Violet))
	sectionStyle  = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(DarkPalette.Blue))
	selectedStyle = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Text)).Background(lipgloss.Color(DarkPalette.Surface)).Bold(true)
	dimStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Secondary))
	keyStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Blue)).Bold(true)
	okStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Green)).Bold(true)
	warnStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Yellow))
	errorStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color(DarkPalette.Red)).Bold(true)
	panelStyle    = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color(DarkPalette.Violet)).Padding(0, 1)
)
