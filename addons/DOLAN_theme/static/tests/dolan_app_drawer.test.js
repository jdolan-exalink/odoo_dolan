import { expect, test } from "@odoo/hoot";

import { DOLAN_UI_PALETTES, DOLAN_THEME_MODES, isSafePosShortcutUrl, normalizeWorkspaceOrder, paletteLinkProperties, customSurfaceProperties, resolveDarkTheme, selectVisibleKpis, selectWorkspaceMetrics, shouldHandleAppDrawerKeydown, sortDesktopApps } from "@DOLAN_theme/js/dolan_app_drawer";
import { iconStyleUsesMask, normalizeIconStyle, resolveActionIconAsset, resolveIconAsset, semanticAppId } from "@DOLAN_theme/js/dolan_icon_registry";

test("theme mode respects explicit light and dark choices", () => {
    expect(resolveDarkTheme("light", true)).toBe(false);
    expect(resolveDarkTheme("dark", false)).toBe(true);
});

test("system theme follows the operating system preference", () => {
    expect(resolveDarkTheme("system", true)).toBe(true);
    expect(resolveDarkTheme("system", false)).toBe(false);
});

test("high contrast is a separate dark accessibility theme", () => {
    expect(resolveDarkTheme("contrast", false)).toBe(true);
    expect(DOLAN_THEME_MODES.map((mode) => mode.id)).toEqual(["light", "dark", "system", "contrast"]);
});

test("theme picker provides the standard DOLAN and alternate color combinations", () => {
    expect(DOLAN_UI_PALETTES.map((palette) => palette.id)).toEqual([
        "dolan", "ocean", "forest", "sunset", "violet", "graphite", "emerald", "custom",
    ]);
    expect(DOLAN_UI_PALETTES[0].label).toBe("ERP");
    expect(DOLAN_UI_PALETTES.every((palette) => palette.primary.startsWith("#") && palette.secondary.startsWith("#"))).toBe(true);
});

test("semantic app names map to stable DOLAN identifiers", () => {
    window.dolanUiIconXmlids = {
        "sale.sale_menu_root": "app.sales",
        "account.menu_finance": "app.invoicing",
        "DOLAN_accounting.menu_dolan_accounting_root": "app.accounting",
        "point_of_sale.menu_point_root": "app.pos",
    };
    expect(semanticAppId({ xmlid: "sale.sale_menu_root", name: "Ventas" })).toBe("app.sales");
    expect(semanticAppId({ xmlid: "account.menu_finance", name: "Facturación" })).toBe("app.invoicing");
    expect(semanticAppId({ xmlid: "DOLAN_accounting.menu_dolan_accounting_root", name: "Contabilidad" })).toBe("app.accounting");
    expect(semanticAppId({ xmlid: "point_of_sale.menu_point_root", name: "Punto de venta" })).toBe("app.pos");
    window.dolanUiIconNames = { "facturacion": "app.invoicing", "facturación": "app.invoicing" };
    expect(semanticAppId({ name: "Facturación" })).toBe("app.invoicing");
    expect(semanticAppId({ name: "Facturación anterior" })).toBe(null);
});

test("icon variants resolve local resources and retain legacy style aliases", () => {
    const assignment = { "app.sales": {
        fluent_3d: "fluent_3d/sales.png",
        fluent_flat: "fluent_flat/sales.svg",
        fluent_filled: "fluent_filled/sales.svg",
        fluent_regular: "fluent_regular/sales.svg",
        tabler: "tabler/chart-pie.svg",
    } };
    expect(resolveIconAsset("app.sales", "fluent_3d_classic", assignment)).toBe("/DOLAN_theme/static/src/lib/fluent_3d/sales.png");
    expect(resolveIconAsset("app.sales")).toBe(null);
    expect(resolveIconAsset("app.sales", "fluent_flat_modern", assignment)).toBe("/DOLAN_theme/static/src/lib/fluent_flat/sales.svg");
    expect(resolveIconAsset("app.sales", "fluent_outline_color", assignment)).toBe("/DOLAN_theme/static/src/lib/fluent_regular/sales.svg");
    expect(resolveIconAsset("app.sales", "tabler", assignment)).toBe("/DOLAN_theme/static/src/lib/tabler/chart-pie.svg");
    expect(resolveIconAsset("app.sales", "odoo_original", assignment)).toBe(null);
    expect(resolveIconAsset("app.whatsapp", "odoo_original", assignment)).toBe(null);
    expect(resolveIconAsset("app.sales", "fluent_3d_classic", { "app.sales": { fluent_3d: "../../secret.png" } })).toBe(null);
    expect(normalizeIconStyle("fluent")).toBe("fluent_3d_classic");
    expect(normalizeIconStyle("unknown_style")).toBe("odoo_original");
    expect(iconStyleUsesMask("fluent_filled_duotone")).toBe(true);
    expect(resolveActionIconAsset("search")).toBe("/DOLAN_theme/static/src/lib/tabler/search.svg");
    expect(resolveIconAsset("app.unknown", "fluent", assignment)).toBe(null);
});

test("legacy Mi Espacio widget preferences can still be read", () => {
    const widgets = [{ key: "quotes_open" }, { key: "invoices_draft" }];
    expect(selectVisibleKpis(widgets, ["quotes_open"]).map((widget) => widget.key)).toEqual(["quotes_open"]);
    expect(selectVisibleKpis(widgets, []).length).toBe(0);
});

test("Mi Espacio summary keeps zero counts while respecting role and personal visibility", () => {
    const metrics = [
        { key: "po_pending", role: "compras", count: 0 },
        { key: "receipts_pending", role: "deposito", count: 3 },
        { key: "my_activities", role: "general", count: 0 },
        { key: "invoices_overdue", role: "administracion", count: 8 },
    ];
    expect(selectWorkspaceMetrics(metrics, metrics.map((metric) => metric.key), "all", [
        "po_pending", "receipts_pending", "my_activities",
    ]).map((metric) => metric.count)).toEqual([0, 3, 0]);
    expect(selectWorkspaceMetrics(metrics, ["po_pending", "my_activities"], "compras", [
        "po_pending", "my_activities",
    ]).map((metric) => metric.key)).toEqual(["po_pending"]);
});

test("Mi Espacio normalizes custom section order and appends missing sections", () => {
    const order = normalizeWorkspaceOrder(["activity", "attention", "invalid", "activity"]);
    expect(order.slice(0, 2)).toEqual(["activity", "attention"]);
    expect(order.length).toBe(6);
    expect(new Set(order).size).toBe(6);
});

test("POS shortcuts only navigate to the native Odoo POS route", () => {
    expect(isSafePosShortcutUrl("/pos/ui?config_id=2")).toBe(true);
    expect(isSafePosShortcutUrl("https://example.invalid/pos/ui?config_id=2")).toBe(false);
    expect(isSafePosShortcutUrl("/web#action=1")).toBe(false);
});

const apps = [
    { id: 1, xmlid: "base.menu_sales", name: "Ventas" },
    { id: 2, xmlid: "base.menu_contacts", name: "Contactos" },
    { id: 3, xmlid: "base.menu_calendar", name: "Calendario" },
];

test("AI composer is excluded from app drawer global keyboard handling", () => {
    const chat = document.createElement("section");
    chat.className = "o_dolan_ai_drawer";
    const textarea = document.createElement("textarea");
    chat.append(textarea);

    const appSearch = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(textarea, appSearch)).toBe(false);
});

test("app drawer search keeps its own keyboard handling", () => {
    const appSearch = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(appSearch, appSearch)).toBe(true);
});

test("other editable fields are excluded from app drawer global keyboard handling", () => {
    const formInput = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(formInput, null)).toBe(false);
});

test("alphabetical order uses translated names and a stable tie break", () => {
    expect(sortDesktopApps(apps, "alphabetical").map((app) => app.id)).toEqual([3, 2, 1]);
});

test("Odoo locale codes with underscores do not break the app drawer", () => {
    expect(sortDesktopApps(apps, "alphabetical", {}, [], "es_AR").map((app) => app.id)).toEqual([3, 2, 1]);
});

test("most used order uses observed counts and alphabetical ties", () => {
    const sorted = sortDesktopApps(apps, "most_used", {
        "base.menu_sales": 4,
        "base.menu_contacts": 4,
        "base.menu_calendar": 0,
    });
    expect(sorted.map((app) => app.id)).toEqual([2, 1, 3]);
});

test("custom order is preserved and newly installed apps are appended alphabetically", () => {
    const sorted = sortDesktopApps(apps, "custom", {}, [
        { menu_key: "base.menu_sales", sequence: 20 },
        { menu_key: "base.menu_contacts", sequence: 10 },
    ]);
    expect(sorted.map((app) => app.id)).toEqual([2, 1, 3]);
});

test("form links follow the selected palette and stay readable in dark mode", () => {
    expect(paletteLinkProperties("#0878b9")["--bs-link-color"]).toBe("#0878b9");
    expect(paletteLinkProperties("#0878b9")["--bs-link-color-rgb"]).toBe("8, 120, 185");
    expect(paletteLinkProperties("#7938d2", true)["--bs-link-color"]).toBe("#ac84e3");
    // Odoo's Bootstrap build has no prefix: the unprefixed names must match.
    expect(paletteLinkProperties("#0878b9")["--link-color"]).toBe("#0878b9");
    expect(paletteLinkProperties("#0878b9")["--link-color-rgb"]).toBe("8, 120, 185");
});

test("custom palette surfaces apply in light mode only, never white panels in dark mode", () => {
    const colors = { background: "#FAFAFA", surface: "#FFFFFF", text: "#111111", border: "#DDDDDD" };
    expect(customSurfaceProperties(colors, false)["--dolan-color-surface-raised"]).toBe("#FFFFFF");
    expect(customSurfaceProperties(colors, true)).toEqual({});
});
