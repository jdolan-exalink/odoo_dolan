package packages

import (
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
)

type ModuleState string

const (
	StateInstalled    ModuleState = "instalado"
	StateActive       ModuleState = "activo"
	StateHidden       ModuleState = "oculto"
	StatePending      ModuleState = "pendiente"
	StateAvailable    ModuleState = "disponible"
	StateIncompatible ModuleState = "incompatible"
	StateUnavailable  ModuleState = "no disponible"
)

type ModuleSpec struct {
	ID          string      `json:"id"`
	Title       string      `json:"title"`
	Version     string      `json:"version"`
	Category    string      `json:"category"`
	Application bool        `json:"application"`
	Depends     []string    `json:"depends"`
	HasData     bool        `json:"has_data"`
	State       ModuleState `json:"state"`
}

// Catalog defines the 18 real repository addons and their actual manifest dependencies.
var Catalog = []ModuleSpec{
	{
		ID:          "DOLAN_base",
		Title:       "Base Argentina, Multi-Empresa & Perfiles",
		Version:     "20.0.1.1.0",
		Category:    "Base",
		Application: true,
		Depends:     []string{"base", "web", "mail", "account", "l10n_ar", "l10n_latam_invoice_document"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_theme",
		Title:       "Estética Web y Mobile (OWL 3)",
		Version:     "20.0.2.51.0",
		Category:    "UI",
		Application: false,
		Depends:     []string{"base", "web", "DOLAN_base"},
		HasData:     false,
	},
	{
		ID:          "DOLAN_accounting",
		Title:       "Contabilidad Pro, Conciliación, Activos y Préstamos",
		Version:     "20.0.1.8.0",
		Category:    "Contabilidad",
		Application: true,
		Depends:     []string{"account", "l10n_ar", "l10n_latam_check"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_l10n_ar_afip",
		Title:       "Facturación Electrónica ARCA/AFIP, Padrón, QR y Libro IVA",
		Version:     "20.0.1.38.0",
		Category:    "Fiscal",
		Application: false,
		Depends:     []string{"web", "account", "account_debit_note", "l10n_ar", "l10n_latam_invoice_document", "certificate", "DOLAN_accounting"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_knowledge_bi",
		Title:       "Base de Conocimiento (Wiki RAG) & Tableros BI",
		Version:     "20.0.1.8.0",
		Category:    "Productividad",
		Application: true,
		Depends:     []string{"base", "mail", "sale_management", "account", "stock", "crm"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_payroll_ar",
		Title:       "Sueldos y Jornales Argentina",
		Version:     "20.0.1.0.0",
		Category:    "Recursos Humanos",
		Application: true,
		Depends:     []string{"hr", "account", "l10n_ar", "mail"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_l10n_ar_cot",
		Title:       "Remito electrónico y COT ARBA",
		Version:     "20.0.1.0.0",
		Category:    "Inventario",
		Application: false,
		Depends:     []string{"l10n_ar_stock"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_bank_ar",
		Title:       "Bancos Argentinos (extractos, impuesto débitos/créditos, echeq)",
		Version:     "20.0.1.0.0",
		Category:    "Contabilidad",
		Application: false,
		Depends:     []string{"DOLAN_accounting", "l10n_latam_check"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_collections",
		Title:       "Cobranza Digital (link de pago, QR, débito por CBU, WhatsApp)",
		Version:     "20.0.1.0.0",
		Category:    "Contabilidad",
		Application: false,
		Depends:     []string{"account", "DOLAN_accounting", "DOLAN_whatsapp"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_exchange",
		Title:       "Cotizaciones USD y Tipo de Cambio BNA",
		Version:     "20.0.1.0.0",
		Category:    "Ventas",
		Application: false,
		Depends:     []string{"base", "sale_management", "account"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_ai",
		Title:       "AI - ChatGPT Plan & Whisper",
		Version:     "20.0.1.34.0",
		Category:    "IA",
		Application: true,
		Depends:     []string{"base", "web", "mail", "base_automation", "DOLAN_knowledge_bi", "DOLAN_exchange"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_ocr",
		Title:       "Extracción OCR de Facturas y Gastos con IA & QR ARCA",
		Version:     "20.0.1.7.0",
		Category:    "IA / Contabilidad",
		Application: false,
		Depends:     []string{"account", "hr_expense", "DOLAN_ai", "DOLAN_l10n_ar_afip"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_whatsapp",
		Title:       "Envíos y WhatsApp",
		Version:     "20.0.1.0.0",
		Category:    "Comunicación",
		Application: true,
		Depends:     []string{"base", "web", "mail", "account"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_pos",
		Title:       "Punto de Venta, Kitchen Display & Cuenta Corriente",
		Version:     "20.0.1.3.0",
		Category:    "Comercio",
		Application: true,
		Depends:     []string{"point_of_sale", "pos_restaurant", "pos_mercado_pago", "DOLAN_payment_terminal", "account", "stock"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_pricelist",
		Title:       "Actualización masiva de precios e historial",
		Version:     "20.0.1.0.0",
		Category:    "Ventas",
		Application: false,
		Depends:     []string{"mail", "product", "sale_management"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_credit_limit",
		Title:       "Límite de crédito con bloqueo de ventas",
		Version:     "20.0.1.0.1",
		Category:    "Contabilidad",
		Application: false,
		Depends:     []string{"sale", "account"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_credit_limit_pos",
		Title:       "Límite de crédito en el Punto de Venta",
		Version:     "20.0.1.0.0",
		Category:    "Comercio",
		Application: false,
		Depends:     []string{"DOLAN_credit_limit", "point_of_sale"},
		HasData:     false,
	},
	{
		ID:          "DOLAN_marketplace",
		Title:       "Mercado Libre y Tiendanube",
		Version:     "20.0.1.0.0",
		Category:    "Ventas",
		Application: false,
		Depends:     []string{"sale_management", "sale_stock"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_account_reports",
		Title:       "Informes contables interactivos y tablero financiero",
		Version:     "20.0.1.0.0",
		Category:    "Contabilidad",
		Application: false,
		Depends:     []string{"account", "spreadsheet_dashboard_account"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_discount_engine",
		Title:       "Promociones y Control de Descuentos POS",
		Version:     "20.0.1.2.0",
		Category:    "Comercio",
		Application: true,
		Depends:     []string{"point_of_sale", "stock"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_payment_terminal",
		Title:       "Terminales de Cobro",
		Version:     "20.0.1.3.0",
		Category:    "Comercio",
		Application: true,
		Depends:     []string{"base", "web", "account"},
		HasData:     true,
	},
	{
		ID:          "ePOS_print",
		Title:       "Impresión Fiscal/Ticket de Punto de Venta (ePOS)",
		Version:     "20.0.1.0.0",
		Category:    "Comercio",
		Application: true,
		Depends:     []string{"point_of_sale", "pos_restaurant"},
		HasData:     false,
	},
	{
		ID:          "pos_scale_management",
		Title:       "Administración de Balanzas POS",
		Version:     "20.0.1.2.0",
		Category:    "Comercio",
		Application: true,
		Depends:     []string{"base", "product", "stock", "point_of_sale", "pos_stock", "barcodes"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_stock_mrp",
		Title:       "Barcode Scanner, Shop Floor MRP & Control de Calidad",
		Version:     "20.0.1.1.0",
		Category:    "Operaciones",
		Application: true,
		Depends:     []string{"stock", "mrp", "hr", "maintenance", "barcodes"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_subscription",
		Title:       "Suscripciones y Facturación Recurrente",
		Version:     "20.0.1.1.0",
		Category:    "Servicios",
		Application: true,
		Depends:     []string{"sale_management", "account", "crm", "project"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_renting",
		Title:       "Gestión de Alquileres (Rental)",
		Version:     "20.0.1.1.0",
		Category:    "Servicios",
		Application: true,
		Depends:     []string{"sale_management", "stock", "account"},
		HasData:     true,
	},
	{
		ID:          "DOLAN_views",
		Title:       "Vistas Avanzadas (Gantt, Cohort, Grid & Map)",
		Version:     "20.0.1.2.0",
		Category:    "Servicios / Proyectos",
		Application: false,
		Depends:     []string{"web", "base", "project"},
		HasData:     true,
	},
}

type ChangePlan struct {
	Installation        string       `json:"installation"`
	CurrentProfile      core.Profile `json:"current_profile"`
	TargetProfile       core.Profile `json:"target_profile"`
	CurrentModules      []string     `json:"current_modules"`
	TargetModules       []string     `json:"target_modules"`
	ToInstall           []string     `json:"to_install"`
	AutoDependencies    []string     `json:"auto_dependencies,omitempty"`
	OdooSystemAppsToAdd []string     `json:"odoo_system_apps_to_add,omitempty"`
	RetainedWithData    []string     `json:"retained_with_data,omitempty"`
	RequestedUninstall  []string     `json:"requested_uninstall,omitempty"`
	BlockedUninstall    []string     `json:"blocked_uninstall,omitempty"`
	RequiresBackup      bool         `json:"requires_backup"`
	Warnings            []string     `json:"warnings,omitempty"`
}

func AllCatalogIDs() []string {
	out := make([]string, 0, len(Catalog))
	for _, m := range Catalog {
		out = append(out, m.ID)
	}
	return out
}

func FindModule(id string) (ModuleSpec, bool) {
	for _, m := range Catalog {
		if m.ID == id {
			return m, true
		}
	}
	return ModuleSpec{}, false
}

// ResolveDependencies expands any requested DOLAN modules with their transitive DOLAN and CE dependencies.
func ResolveDependencies(requested []string) (dolanMods []string, autoAdded []string, ceDeps []string, err error) {
	reqSet := make(map[string]bool)
	for _, r := range requested {
		r = strings.TrimSpace(r)
		if r == "" {
			continue
		}
		if _, ok := FindModule(r); !ok {
			return nil, nil, nil, fmt.Errorf("módulo no disponible en el catálogo: %s", r)
		}
		reqSet[r] = true
	}

	resolved := make(map[string]bool)
	ceSet := make(map[string]bool)

	var visit func(id string)
	visit = func(id string) {
		if resolved[id] {
			return
		}
		spec, ok := FindModule(id)
		if !ok {
			ceSet[id] = true
			return
		}
		resolved[id] = true
		for _, dep := range spec.Depends {
			if _, isDolan := FindModule(dep); isDolan {
				visit(dep)
			} else {
				ceSet[dep] = true
			}
		}
	}

	for _, m := range Catalog {
		if reqSet[m.ID] {
			visit(m.ID)
		}
	}

	for _, m := range Catalog {
		if resolved[m.ID] {
			dolanMods = append(dolanMods, m.ID)
			if !reqSet[m.ID] {
				autoAdded = append(autoAdded, m.ID)
			}
		}
	}
	for dep := range ceSet {
		ceDeps = append(ceDeps, dep)
	}
	sort.Strings(ceDeps)
	return dolanMods, autoAdded, ceDeps, nil
}

// PlanChange computes an incremental package transition (e.g. Servicios -> Comercio or adding individual modules).
// Lowering a profile NEVER automatically uninstalls modules that contain data.
func PlanChange(installationName string, currentProfile, targetProfile core.Profile, currentInstalled, addModules, removeModules []string) (ChangePlan, error) {
	instSet := make(map[string]bool)
	for _, m := range currentInstalled {
		instSet[m] = true
	}

	desiredSet := make(map[string]bool)
	for _, m := range currentInstalled {
		desiredSet[m] = true
	}

	var retained []string
	if targetProfile != "" && core.CanonicalProfile(targetProfile) != core.ProfileCustom {
		info := core.FindProfileInfo(targetProfile)
		profileSet := make(map[string]bool)
		for _, m := range info.DolanModules {
			profileSet[m] = true
			desiredSet[m] = true
		}
		for _, existing := range currentInstalled {
			if !profileSet[existing] {
				retained = append(retained, existing)
			}
		}
	} else if targetProfile == "" {
		targetProfile = currentProfile
	}

	for _, m := range addModules {
		m = strings.TrimSpace(m)
		if m != "" {
			desiredSet[m] = true
		}
	}

	var requestedList []string
	for m := range desiredSet {
		requestedList = append(requestedList, m)
	}

	resolvedDolan, autoDeps, ceDeps, err := ResolveDependencies(requestedList)
	if err != nil {
		return ChangePlan{}, err
	}

	var toInstall []string
	for _, m := range resolvedDolan {
		if !instSet[m] {
			toInstall = append(toInstall, m)
		}
	}

	plan := ChangePlan{
		Installation:        installationName,
		CurrentProfile:      core.CanonicalProfile(currentProfile),
		TargetProfile:       core.CanonicalProfile(targetProfile),
		CurrentModules:      currentInstalled,
		TargetModules:       resolvedDolan,
		ToInstall:           toInstall,
		AutoDependencies:    autoDeps,
		OdooSystemAppsToAdd: ceDeps,
		RetainedWithData:    retained,
		RequestedUninstall:  removeModules,
	}

	if len(retained) > 0 {
		plan.Warnings = append(plan.Warnings, fmt.Sprintf("Protección de datos: los módulos ya instalados (%s) se conservan activos para no eliminar tablas ni registros al cambiar de perfil.", strings.Join(retained, ", ")))
	}

	if len(removeModules) > 0 {
		for _, rm := range removeModules {
			spec, ok := FindModule(rm)
			if !ok {
				return ChangePlan{}, fmt.Errorf("módulo desconocido para desinstalar: %s", rm)
			}
			// Check if any installed module depends on rm
			var dependents []string
			for _, otherID := range resolvedDolan {
				if otherID == rm {
					continue
				}
				if otherSpec, ok := FindModule(otherID); ok {
					for _, dep := range otherSpec.Depends {
						if dep == rm {
							dependents = append(dependents, otherID)
						}
					}
				}
			}
			if len(dependents) > 0 {
				plan.BlockedUninstall = append(plan.BlockedUninstall, fmt.Sprintf("%s (requerido por: %s)", rm, strings.Join(dependents, ", ")))
			} else if spec.HasData {
				plan.BlockedUninstall = append(plan.BlockedUninstall, fmt.Sprintf("%s (contiene modelos con datos persistentes; ocultá/desactivá el acceso en lugar de desinstalar)", rm))
			}
		}
		if len(plan.BlockedUninstall) > 0 {
			return plan, errors.New("desinstalación bloqueada por seguridad de datos o módulos dependientes: " + strings.Join(plan.BlockedUninstall, "; "))
		}
		plan.RequiresBackup = true
	}

	return plan, nil
}
