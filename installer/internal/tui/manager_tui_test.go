package tui

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/packages"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
)

func TestAllScreensRenderAndAdapt(t *testing.T) {
	m := NewManagerModel(context.Background(), t.TempDir(), "")
	m.Installations = []ManagedItem{
		{ID: "101", VMID: 101, Name: "Frigorífico", Profile: "Comercio", RawProfile: core.ProfileCommerce, Active: true},
		{ID: "105", VMID: 105, Name: "Desarrollo", Profile: "Completo", RawProfile: core.ProfileComplete, DemoData: true, DemoMode: "dolan", Active: false},
	}
	m.initPackageModifier()

	screens := []struct {
		id       ScreenID
		expected string
	}{
		{ScreenHome, "DOLAN MANAGER"},
		{ScreenChooseTarget, "¿Dónde querés instalar DOLAN?"},
		{ScreenLXCConfig, "Paso 2 de 6"},
		{ScreenSelectPackages, "Seleccioná un perfil inicial"},
		{ScreenCompanyAndDemo, "DATOS DEMO"},
		{ScreenConfirmDeploy, "Confirmar instalación"},
		{ScreenInstallProgress, "Progreso general"},
		{ScreenManageInstall, "Borrar instalación"},
		{ScreenManagePackages, "Cambios pendientes"},
		{ScreenCreateBackup, "Incluir filestore"},
		{ScreenBackupProgress, "Exportación PostgreSQL"},
		{ScreenRestoreBackup, "Analizar compatibilidad"},
		{ScreenMigration, "Iniciar migración"},
		{ScreenUpdates, "Crear backup antes de actualizar"},
		{ScreenConfiguration, "Backups programados"},
		{ScreenDiagnostics, "Exportar diagnóstico"},
		{ScreenDeleteConfirm, "Confirmar borrado definitivo"},
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

	// Home screen must explicitly tag DEMO installations and include Borrar instalación
	m.Screen = ScreenHome
	homeOut := RenderScreen(m)
	if !strings.Contains(homeOut, "DEMO") || !strings.Contains(homeOut, "Borrar instalación") {
		t.Fatalf("expected DEMO label and Borrar instalación on home screen, got:\n%s", homeOut)
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

func TestPackageModifierAndDeleteFlowInTUI(t *testing.T) {
	root := t.TempDir()
	instPath := filepath.Join(root, "empresa_test")
	if err := os.MkdirAll(instPath, 0750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(instPath, "docker-compose.yml"), []byte("services:\n  odoo:\n    image: odoo:20.0\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(instPath, ".env"), []byte("DOLAN_PROFILE=basico\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := state.Write(instPath, state.Manifest{
		Name:        "empresa_test",
		Company:     "Empresa Test SA",
		Profile:     "basico",
		Modules:     core.FindProfileInfo(core.ProfileBasic).DolanModules,
		ProjectPath: instPath,
	}); err != nil {
		t.Fatal(err)
	}

	m := NewManagerModel(context.Background(), root, "")
	if len(m.Installations) != 1 {
		t.Fatalf("expected 1 discovered installation, got %d", len(m.Installations))
	}

	// 1. Navigate to ScreenManagePackages
	m.navigate(ScreenManagePackages)
	if m.PkgCurrentProfile != core.ProfileBasic {
		t.Fatalf("expected initial profile basico, got %s", m.PkgCurrentProfile)
	}

	// 2. Find an available module (e.g. DOLAN_stock_mrp) and toggle it on
	mrpIdx := -1
	for i, spec := range packages.Catalog {
		if spec.ID == "DOLAN_stock_mrp" {
			mrpIdx = i
			break
		}
	}
	if mrpIdx < 0 {
		t.Fatal("DOLAN_stock_mrp not found in catalog")
	}
	m.Cursor = mrpIdx
	m = m.togglePackageAtCursor()
	if !m.PkgAdded["DOLAN_stock_mrp"] {
		t.Fatal("expected DOLAN_stock_mrp to be marked for installation")
	}
	if len(m.PkgPlan.ToInstall) == 0 {
		t.Fatal("expected pending modules in PkgPlan.ToInstall")
	}

	// 3. Switch target profile to Comercio and apply changes
	m.PkgTargetIdx = 2 // Comercio
	m.recalcPackagePlan()
	m = m.applyPackageChanges()
	if m.Installations[0].RawProfile != core.ProfileCommerce {
		t.Fatalf("expected installation profile to update to comercio, got %s", m.Installations[0].RawProfile)
	}
	savedManifest, err := state.Read(instPath)
	if err != nil {
		t.Fatalf("read updated manifest: %v", err)
	}
	if savedManifest.Profile != "comercio" {
		t.Fatalf("expected saved manifest profile comercio, got %s", savedManifest.Profile)
	}

	// 4. Test Delete Confirmation: first cancel (Cursor=0), then confirm (Cursor=1)
	m.navigate(ScreenDeleteConfirm)
	m.Cursor = 0
	modelAfterCancel, _ := m.handleEnter()
	m = modelAfterCancel.(ManagerModel)
	if _, err := os.Stat(instPath); err != nil {
		t.Fatalf("expected installation to remain after canceling delete: %v", err)
	}

	m.navigate(ScreenDeleteConfirm)
	m.Cursor = 1
	modelAfterConfirm, _ := m.handleEnter()
	m = modelAfterConfirm.(ManagerModel)
	if len(m.Installations) != 0 {
		t.Fatalf("expected 0 installations after delete, got %d", len(m.Installations))
	}
	if _, err := os.Stat(instPath); !os.IsNotExist(err) {
		t.Fatalf("expected installation directory %s to be deleted", instPath)
	}
}
