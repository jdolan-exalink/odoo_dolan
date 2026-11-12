package packages

import (
	"testing"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
)

func TestProfileTransitionServicesToCommercePreservesData(t *testing.T) {
	servicesInfo := core.FindProfileInfo(core.ProfileServices)
	plan, err := PlanChange("105", core.ProfileServices, core.ProfileCommerce, servicesInfo.DolanModules, nil, nil)
	if err != nil {
		t.Fatalf("PlanChange failed: %v", err)
	}
	if len(plan.ToInstall) == 0 {
		t.Fatal("expected Commerce modules (DOLAN_pos, etc.) to be queued for installation")
	}
	// Must retain DOLAN_subscription and DOLAN_renting without uninstalling them
	foundSub := false
	for _, r := range plan.RetainedWithData {
		if r == "DOLAN_subscription" {
			foundSub = true
		}
	}
	if !foundSub {
		t.Fatalf("expected DOLAN_subscription to be retained on profile change, got %+v", plan.RetainedWithData)
	}
}

func TestAddIndividualModuleAndTransitiveDependencies(t *testing.T) {
	// Adding DOLAN_ocr must automatically pull DOLAN_ai, DOLAN_knowledge_bi, DOLAN_exchange, DOLAN_l10n_ar_afip, DOLAN_accounting
	mods, autoAdded, _, err := ResolveDependencies([]string{"DOLAN_ocr"})
	if err != nil {
		t.Fatal(err)
	}
	if len(mods) < 5 || len(autoAdded) < 4 {
		t.Fatalf("expected transitive dependencies for DOLAN_ocr, got mods=%v auto=%v", mods, autoAdded)
	}
}

func TestDolanPOSResolvesPaymentTerminalAndMercadoPago(t *testing.T) {
	mods, autoAdded, ceDeps, err := ResolveDependencies([]string{"DOLAN_pos"})
	if err != nil {
		t.Fatal(err)
	}
	if !hasCatalogEntry(mods, "DOLAN_payment_terminal") || !hasCatalogEntry(autoAdded, "DOLAN_payment_terminal") {
		t.Fatalf("DOLAN_pos must pull in its DOLAN terminal dependency; mods=%v auto=%v", mods, autoAdded)
	}
	if !hasCatalogEntry(ceDeps, "pos_mercado_pago") {
		t.Fatalf("DOLAN_pos must install the Odoo Mercado Pago provider; CE deps=%v", ceDeps)
	}
}

func TestCommerceAndCompleteProfilesInstallMercadoPagoProvider(t *testing.T) {
	for _, profile := range []core.Profile{core.ProfileCommerce, core.ProfileComplete} {
		info := core.FindProfileInfo(profile)
		if !hasCatalogEntry(info.SystemApps, "pos_mercado_pago") {
			t.Errorf("profile %s must explicitly install pos_mercado_pago", profile)
		}
	}
}

func hasCatalogEntry(entries []string, expected string) bool {
	for _, entry := range entries {
		if entry == expected {
			return true
		}
	}
	return false
}

func TestBlockUninstallModuleWithDataOrDependents(t *testing.T) {
	current := []string{"DOLAN_base", "DOLAN_theme", "DOLAN_accounting", "DOLAN_l10n_ar_afip"}
	_, err := PlanChange("105", core.ProfileBasic, core.ProfileBasic, current, nil, []string{"DOLAN_accounting"})
	if err == nil {
		t.Fatal("expected uninstalling DOLAN_accounting (with dependent DOLAN_l10n_ar_afip and data) to be blocked")
	}
}

func TestPersonalPackagesKeepPayrollOptional(t *testing.T) {
	operativo, _, ceDeps, err := ResolveDependencies([]string{"DOLAN_personal_operativo"})
	if err != nil {
		t.Fatal(err)
	}
	if hasCatalogEntry(operativo, "DOLAN_payroll_ar") {
		t.Fatalf("Personal Operativo must not install payroll; got %v", operativo)
	}
	if !hasCatalogEntry(operativo, "DOLAN_hr_core") || !hasCatalogEntry(ceDeps, "hr_holidays") || !hasCatalogEntry(ceDeps, "hr_attendance") {
		t.Fatalf("Personal Operativo must pull core, time off and attendance; mods=%v ce=%v", operativo, ceDeps)
	}
	completo, _, _, err := ResolveDependencies([]string{"DOLAN_personal"})
	if err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"DOLAN_personal_operativo", "DOLAN_hr_core", "DOLAN_payroll_ar"} {
		if !hasCatalogEntry(completo, id) {
			t.Fatalf("Personal Completo must include %s; got %v", id, completo)
		}
	}
	info := core.FindProfileInfo(core.ProfileComplete)
	if !hasCatalogEntry(info.DolanModules, "DOLAN_personal") {
		t.Fatalf("profile Completo must install the Personal package")
	}
}
