package tui

import (
	"context"
	"strings"
	"testing"
)

func TestAllSixteenScreensRenderAndAdapt(t *testing.T) {
	m := NewManagerModel(context.Background(), t.TempDir(), "")
	m.Installations = []ManagedItem{
		{ID: "101", VMID: 101, Name: "Frigorífico", Profile: "Comercio", Active: true},
		{ID: "105", VMID: 105, Name: "Desarrollo", Profile: "Completo", DemoData: true, DemoMode: "dolan", Active: false},
	}

	screens := []struct {
		id       ScreenID
		expected string
	}{
		{ScreenHome, "DOLAN MANAGER"},
		{ScreenChooseTarget, "¿Dónde querés instalar DOLAN?"},
		{ScreenLXCConfig, "Paso 2 de 6"},
		{ScreenSelectPackages, "Seleccioná un perfil inicial"},
		{ScreenCompanyAndDemo, "DATOS DE DEMOSTRACIÓN"},
		{ScreenConfirmDeploy, "Confirmar instalación"},
		{ScreenInstallProgress, "Progreso general"},
		{ScreenManageInstall, "Administrar paquetes"},
		{ScreenManagePackages, "Cambios pendientes"},
		{ScreenCreateBackup, "Incluir filestore"},
		{ScreenBackupProgress, "Exportación PostgreSQL"},
		{ScreenRestoreBackup, "Analizar compatibilidad"},
		{ScreenMigration, "Iniciar migración"},
		{ScreenUpdates, "Crear backup antes de actualizar"},
		{ScreenConfiguration, "Backups programados"},
		{ScreenDiagnostics, "Exportar diagnóstico"},
	}

	dimensions := [][2]int{{120, 35}, {100, 30}, {80, 24}}
	for _, dim := range dimensions {
		m.Width, m.Height = dim[0], dim[1]
		for _, sc := range screens {
			m.Screen = sc.id
			out := RenderScreen(m)
			if !strings.Contains(out, sc.expected) {
				t.Fatalf("screen %s at %dx%d missing %q:\n%s", sc.id, dim[0], dim[1], sc.expected, out)
			}
		}
	}

	// Home screen must explicitly tag DEMO installations
	m.Screen = ScreenHome
	homeOut := RenderScreen(m)
	if !strings.Contains(homeOut, "DEMO") {
		t.Fatalf("expected DEMO label on home screen, got:\n%s", homeOut)
	}

	// Test ASCII fallback and NO_COLOR mode (Requirement 6 & Test 22)
	m.Palette.ASCIIOnly = true
	m.Palette.NoColor = true
	m.Screen = ScreenInstallProgress
	asciiOut := RenderScreen(m)
	if !strings.Contains(asciiOut, "[OK]") || strings.Contains(asciiOut, "█") {
		t.Fatalf("expected ASCII fallback glyphs without Unicode blocks, got:\n%s", asciiOut)
	}

	// Compact terminal (< 50 cols)
	m.Width = 40
	m.Height = 12
	compactOut := RenderScreen(m)
	if !strings.Contains(compactOut, "Modo compacto") {
		t.Fatalf("expected compact fallback message, got:\n%s", compactOut)
	}
}
