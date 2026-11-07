package core

import "strings"

type ProfileInfo struct {
	ID             Profile  `json:"id"`
	LegacyID       Profile  `json:"legacy_id,omitempty"`
	Title          string   `json:"title"`
	Summary        string   `json:"summary"`
	FeatureBullets []string `json:"feature_bullets"`
	SystemApps     []string `json:"system_apps"`
	DolanModules   []string `json:"dolan_modules"`
}

var ProfileCatalog = []ProfileInfo{
	{
		ID:       ProfileBasic,
		LegacyID: ProfileCore,
		Title:    "Básico",
		Summary:  "Contactos, usuarios, facturación ARCA, ventas, stock, IA/OCR, WhatsApp y tema",
		FeatureBullets: []string{
			"Contactos", "Usuarios", "Facturación argentina",
			"Ventas", "WhatsApp", "IA / OCR",
		},
		SystemApps: []string{
			"contacts", "calendar", "mail", "crm", "sale_management", "purchase", "stock",
			"l10n_ar", "l10n_ar_withholding", "l10n_ar_pos", "l10n_ar_stock",
			"l10n_latam_check", "l10n_latam_invoice_document",
		},
		DolanModules: []string{
			"DOLAN_base", "DOLAN_theme", "DOLAN_l10n_ar_afip", "DOLAN_accounting",
			"DOLAN_ai", "DOLAN_ocr", "DOLAN_whatsapp", "DOLAN_knowledge_bi",
		},
	},
	{
		ID:      ProfileServices,
		Title:   "Servicios",
		Summary: "Básico más CRM, proyectos, suscripciones, alquileres, vistas avanzadas y BI",
		FeatureBullets: []string{
			"CRM", "Ventas", "Facturación",
			"Proyectos", "Suscripciones", "Alquileres",
		},
		SystemApps: []string{
			"contacts", "calendar", "mail", "crm", "sale_management", "purchase", "stock",
			"project", "project_todo",
			"l10n_ar", "l10n_ar_withholding", "l10n_ar_pos", "l10n_ar_stock",
			"l10n_latam_check", "l10n_latam_invoice_document",
		},
		DolanModules: []string{
			"DOLAN_base", "DOLAN_theme", "DOLAN_l10n_ar_afip", "DOLAN_accounting",
			"DOLAN_ai", "DOLAN_ocr", "DOLAN_whatsapp", "DOLAN_subscription",
			"DOLAN_renting", "DOLAN_views", "DOLAN_knowledge_bi",
		},
	},
	{
		ID:      ProfileCommerce,
		Title:   "Comercio",
		Summary: "Compras, ventas, inventario, POS, descuentos, terminales y facturación argentina",
		FeatureBullets: []string{
			"Contactos", "Ventas", "Compras",
			"Inventario", "POS", "Facturación argentina",
		},
		SystemApps: []string{
			"contacts", "calendar", "mail", "crm", "sale_management", "purchase", "stock",
			"point_of_sale", "pos_restaurant",
			"l10n_ar", "l10n_ar_withholding", "l10n_ar_pos", "l10n_ar_stock",
			"l10n_latam_check", "l10n_latam_invoice_document",
		},
		DolanModules: []string{
			"DOLAN_base", "DOLAN_theme", "DOLAN_l10n_ar_afip", "DOLAN_accounting",
			"DOLAN_ai", "DOLAN_ocr", "DOLAN_whatsapp", "DOLAN_pos",
			"DOLAN_discount_engine", "DOLAN_payment_terminal", "DOLAN_knowledge_bi",
			"ePOS_print", "pos_scale_management",
		},
	},
	{
		ID:       ProfileComplete,
		LegacyID: ProfileFull,
		Title:    "Completo",
		Summary:  "Catálogo DOLAN completo y aplicaciones CE compatibles (integraciones externas desactivadas)",
		FeatureBullets: []string{
			"Contactos", "Ventas / CRM", "Compras / Stock / MRP",
			"POS / Terminales", "Suscripciones / Alquileres", "Facturación ARCA / BI / IA",
		},
		SystemApps: []string{
			"contacts", "calendar", "mail", "crm", "sale_management", "purchase", "stock",
			"mrp", "point_of_sale", "pos_restaurant", "project", "project_todo",
			"hr", "hr_expense", "hr_skills", "fleet", "maintenance",
			"l10n_ar", "l10n_ar_withholding", "l10n_ar_pos", "l10n_ar_stock",
			"l10n_latam_check", "l10n_latam_invoice_document",
		},
		DolanModules: []string{
			"DOLAN_base", "DOLAN_theme", "DOLAN_l10n_ar_afip", "DOLAN_accounting",
			"DOLAN_ai", "DOLAN_ocr", "DOLAN_whatsapp", "DOLAN_views",
			"DOLAN_pos", "DOLAN_stock_mrp", "DOLAN_subscription", "DOLAN_renting",
			"DOLAN_knowledge_bi", "DOLAN_exchange", "DOLAN_discount_engine",
			"DOLAN_payment_terminal", "ePOS_print", "pos_scale_management",
		},
	},
	{
		ID:      ProfileCustom,
		Title:   "Personalizado",
		Summary: "Selección individual de módulos del catálogo con resolución de dependencias",
		FeatureBullets: []string{
			"Selección individual", "Resolución de dependencias", "Sin reinstalar",
		},
	},
}

func FindProfileInfo(p Profile) ProfileInfo {
	canon := CanonicalProfile(p)
	for _, info := range ProfileCatalog {
		if info.ID == canon || info.LegacyID == p {
			return info
		}
	}
	return ProfileCatalog[0]
}

func ProfileDisplayName(p Profile) string {
	switch CanonicalProfile(p) {
	case ProfileBasic:
		return "Básico"
	case ProfileServices:
		return "Servicios"
	case ProfileCommerce:
		return "Comercio"
	case ProfileComplete:
		return "Completo"
	case ProfileCustom:
		return "Personalizado"
	default:
		s := string(p)
		if s == "" {
			return "Básico"
		}
		return strings.ToUpper(s[:1]) + s[1:]
	}
}
