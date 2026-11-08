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
