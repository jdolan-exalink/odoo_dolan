/** @odoo-module **/

export const DOLAN_ACTION_ICONS = {
    search: "search", plus: "plus", folder: "folder", "folder-plus": "folder-plus",
    star: "star", "sort-az": "arrows-sort", history: "history", settings: "settings",
    check: "circle-check", "alert-triangle": "alert-triangle", "alert-circle": "info-circle",
    calendar: "calendar-event", pencil: "adjustments", cart: "shopping-cart", store: "building-store", "user-plus": "user-plus",
    money: "cash", chat: "messages", bank: "building-store", sparkles: "sparkles", sun: "sun",
    moon: "moon", truck: "devices", factory: "tool", wrench: "tool", tasks: "clipboard-check",
    grid: "layout-grid", dashboard: "layout-dashboard", bolt: "sparkles", clock: "history",
    compress: "arrows-sort", "file-text": "file-text", "x-circle": "x",
    "chart-bar": "chart-bar",
};

const STYLE_ASSET_KEYS = {
    mosaic: "fluent_filled",
    mosaic_brand: "fluent_filled",
    outline: "fluent_regular",
    fluent_3d_classic: "fluent_3d",
    fluent_3d_soft: "fluent_3d",
    fluent_flat_modern: "fluent_flat",
    fluent_flat_clean: "fluent_flat",
    fluent_filled_pro: "fluent_filled",
    fluent_filled_duotone: "fluent_filled",
    fluent_outline_color: "fluent_regular",
    fluent_outline_minimal: "fluent_regular",
    fluent: "fluent_3d", // persisted setting from the first icon release
    tabler: "tabler", // persisted setting from the first icon release
    odoo_original: null,
};

function normalizeLabel(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toLocaleLowerCase();
}

export function semanticAppId(app) {
    const xmlid = String(app?.xmlid || "").trim().toLowerCase();
    const xmlidMap = window.dolanUiIconXmlids || {};
    if (xmlid && xmlidMap[xmlid]) return xmlidMap[xmlid];

    const nameMap = window.dolanUiIconNames || {};
    return nameMap[normalizeLabel(app?.name)] || null;
}

export function resolveIconAsset(semanticId, iconStyle = "odoo_original", assignments = {}) {
    // `null` is intentional for Odoo Original: use native webIcon/webIconData.
    const family = Object.prototype.hasOwnProperty.call(STYLE_ASSET_KEYS, iconStyle)
        ? STYLE_ASSET_KEYS[iconStyle]
        : STYLE_ASSET_KEYS.fluent_3d_classic;
    if (iconStyle === "odoo_original") return null;
    if (!semanticId || !family) return null;
    // Keep the WhatsApp brand recognizable. Barcode and scale use their
    // style-specific catalog assets below so Filled, Outline and Tabler do
    // not accidentally fall back to the same Fluent Flat artwork.
    if (semanticId === "app.whatsapp" && family !== "tabler") {
        return iconStyleUsesMask(iconStyle)
            ? "/DOLAN_theme/static/src/lib/fluent_regular/whatsapp_mask.svg"
            : "/DOLAN_theme/static/src/lib/fluent_flat/whatsapp_brand.svg";
    }
    const relativePath = assignments[semanticId]?.[family];
    if (typeof relativePath !== "string" || !relativePath) return null;
    if (!/^(fluent_3d|fluent_flat|fluent_filled|fluent_regular|fluent|tabler)\/[a-z0-9_-]+\.(png|svg)$/i.test(relativePath)) {
        return null;
    }
    return `/DOLAN_theme/static/src/lib/${relativePath}`;
}

export function resolveActionIconAsset(name, filled = false) {
    const asset = DOLAN_ACTION_ICONS[name];
    if (!asset) return null;
    const filledAsset = ["star", "circle-check", "folder", "bookmark"].includes(asset);
    return filled && filledAsset
        ? `/DOLAN_theme/static/src/lib/tabler/filled/${asset}.svg`
        : `/DOLAN_theme/static/src/lib/tabler/${asset}.svg`;
}

export const MASK_ICON_STYLES = ["mosaic", "mosaic_brand", "outline", "fluent_filled_pro", "fluent_filled_duotone", "fluent_outline_color", "fluent_outline_minimal", "tabler"];

export function iconStyleUsesMask(iconStyle = "odoo_original") {
    return MASK_ICON_STYLES.includes(iconStyle);
}

export function iconStyleUsesTile(iconStyle = "odoo_original") {
    return ["mosaic", "mosaic_brand"].includes(iconStyle);
}

/**
 * Color de cada área para los estilos Mosaico y Contorno. El área sale de la
 * categoría del catálogo de iconos, así todas las apps de Finanzas comparten
 * color, todas las de Comercial otro, etc.
 */
export const ICON_AREA_COLORS = {
    finance: ["#4b8df8", "#1d4ed8"],
    commerce: ["#9b74f7", "#6430d4"],
    operations: ["#fb9a52", "#d9530f"],
    people: ["#2cc3d6", "#0a8299"],
    communication: ["#3fcf96", "#0d8457"],
    productivity: ["#f6bd3a", "#c27803"],
    analytics: ["#f178b0", "#c42d72"],
    knowledge: ["#7f8cf5", "#4348c9"],
    technology: ["#7f8cf5", "#4348c9"],
    tools: ["#8a95a6", "#4a5568"],
};

export function iconAreaColors(semanticId) {
    const category = window.dolanUiIconCatalog?.[semanticId]?.category;
    return ICON_AREA_COLORS[category] || ICON_AREA_COLORS.tools;
}

/** CSS custom properties for a masked app icon (glyph + tile/outline colors). */
export function appIconTileStyle(semanticId, iconStyle, url) {
    if (!url) return "";
    const [light, deep] = iconAreaColors(semanticId);
    let tile = `--dolan-icon-tile-1: ${light}; --dolan-icon-tile-2: ${deep}`;
    if (iconStyle === "mosaic_brand") {
        tile = "--dolan-icon-tile-1: color-mix(in srgb, var(--dolan-color-primary) 78%, #ffffff); --dolan-icon-tile-2: var(--dolan-color-primary)";
    }
    return `--dolan-icon-mask-image: url("${url}"); --dolan-icon-accent: ${deep}; ${tile}`;
}

export function normalizeIconStyle(iconStyle) {
    const aliases = {
        fluent: "fluent_3d_classic",
        fluent_3d_soft: "fluent_3d_classic",
        fluent_flat_modern: "fluent_3d_classic",
        fluent_flat_clean: "fluent_3d_classic",
        fluent_filled_pro: "outline",
        fluent_filled_duotone: "outline",
        fluent_outline_color: "outline",
        fluent_outline_minimal: "outline",
        tabler: "outline",
    };
    if (aliases[iconStyle]) return aliases[iconStyle];
    return ["mosaic", "mosaic_brand", "outline", "fluent_3d_classic", "odoo_original"].includes(iconStyle)
        ? iconStyle
        : "odoo_original";
}
