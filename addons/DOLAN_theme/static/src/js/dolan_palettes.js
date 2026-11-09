/** @odoo-module **/

/**
 * Paletas de la interfaz. Cada paleta define, además del primario y el
 * secundario, la barra superior y el fondo en claro, y su propia versión
 * oscura (fondo, superficie, barra y primario aclarado), para que el cambio
 * de paleta se note en toda la pantalla y no solo en los botones.
 * Los identificadores son los históricos: no cambian para no migrar datos.
 */
export const DOLAN_UI_PALETTES = [
    {
        id: "dolan", label: "Índigo", hint: "Índigo y verde azulado", primary: "#4f46e5", secondary: "#0d9488",
        navbar: "#312e81", canvas: "#f4f5fc",
        dark: { primary: "#8b85f7", secondary: "#3cc9b8", navbar: "#191a3c", canvas: "#11122a", surface: "#1b1d3a" },
    },
    {
        id: "ocean", label: "Océano", hint: "Azul y celeste", primary: "#0b63ce", secondary: "#0aa5c2",
        navbar: "#0b3b75", canvas: "#f2f6fc",
        dark: { primary: "#5aa6f6", secondary: "#3fd0e6", navbar: "#0f1e35", canvas: "#0c1727", surface: "#14233a" },
    },
    {
        id: "emerald", label: "Turquesa", hint: "Petróleo y coral", primary: "#0e7c86", secondary: "#e0674a",
        navbar: "#0b4f56", canvas: "#f1f8f8",
        dark: { primary: "#45c3c9", secondary: "#f39074", navbar: "#0f2427", canvas: "#0b1c1e", surface: "#13292c" },
    },
    {
        id: "forest", label: "Bosque", hint: "Verde y oliva", primary: "#2f7d32", secondary: "#8a9a1c",
        navbar: "#1f4d22", canvas: "#f4f8f1",
        dark: { primary: "#6dc072", secondary: "#c1d24a", navbar: "#152114", canvas: "#10190f", surface: "#1a2719" },
    },
    {
        id: "sunset", label: "Terracota", hint: "Terracota y ámbar", primary: "#c2410c", secondary: "#b7791f",
        navbar: "#7c2d12", canvas: "#fbf6f1",
        dark: { primary: "#f28b5c", secondary: "#f0b54f", navbar: "#241912", canvas: "#1c140f", surface: "#2a1e17" },
    },
    {
        id: "violet", label: "Ciruela", hint: "Ciruela y oro viejo", primary: "#86286e", secondary: "#b8860b",
        navbar: "#561845", canvas: "#faf4f8",
        dark: { primary: "#d983c4", secondary: "#e5b94e", navbar: "#231622", canvas: "#1b111b", surface: "#2a1b29" },
    },
    {
        id: "graphite", label: "Grafito", hint: "Grafito y azul acero", primary: "#334155", secondary: "#2f80ed",
        navbar: "#1f2937", canvas: "#f3f4f6",
        dark: { primary: "#a3b1c4", secondary: "#6aa8ff", navbar: "#14171b", canvas: "#0f1114", surface: "#191c21" },
    },
    {
        id: "custom", label: "Personalizada", hint: "Tus seis colores", primary: "#714b67", secondary: "#017e84",
        navbar: null, canvas: null, dark: null,
    },
];

const HEX = /^#?[\da-f]{6}$/i;

export function hexToRgb(value) {
    const hex = HEX.test(String(value || "")) ? String(value).replace("#", "") : "4f46e5";
    return hex.match(/[\da-f]{2}/gi).map((part) => parseInt(part, 16));
}

export function mixHex(color, target, amount) {
    const a = hexToRgb(color);
    const b = hexToRgb(target);
    return `#${a.map((channel, index) => Math.round(channel + (b[index] - channel) * amount).toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Colores completos de una paleta para un modo. Para "company" y "custom"
 * (solo traen primario y secundario) la barra y los fondos se derivan del
 * primario, igual que en las paletas fijas.
 */
export function resolvePaletteColors(paletteId, { dark = false, company = {}, custom = {} } = {}) {
    const selected = DOLAN_UI_PALETTES.find((item) => item.id === paletteId) || DOLAN_UI_PALETTES[0];
    let primary = selected.primary;
    let secondary = selected.secondary;
    if (paletteId === "company") {
        primary = HEX.test(company.primary || "") ? company.primary : "#714b67";
        secondary = HEX.test(company.secondary || "") ? company.secondary : "#017e84";
    } else if (paletteId === "custom") {
        primary = HEX.test(custom.primary || "") ? custom.primary : selected.primary;
        secondary = HEX.test(custom.secondary || "") ? custom.secondary : selected.secondary;
    }
    const derived = !selected.dark || ["company", "custom"].includes(paletteId);
    if (dark) {
        if (!derived) {
            return { primary: selected.dark.primary, secondary: selected.dark.secondary, navbar: selected.dark.navbar,
                canvas: selected.dark.canvas, surface: selected.dark.surface };
        }
        return {
            primary: mixHex(primary, "#ffffff", 0.38),
            secondary: mixHex(secondary, "#ffffff", 0.3),
            navbar: mixHex(primary, "#101218", 0.78),
            canvas: mixHex(primary, "#11131a", 0.9),
            surface: mixHex(primary, "#1c1f28", 0.88),
        };
    }
    if (!derived) {
        return { primary, secondary, navbar: selected.navbar, canvas: selected.canvas, surface: "#ffffff" };
    }
    return {
        primary,
        secondary,
        navbar: mixHex(primary, "#000000", 0.35),
        canvas: paletteId === "custom" && HEX.test(custom.background || "") ? custom.background : mixHex(primary, "#f7f8fc", 0.95),
        surface: paletteId === "custom" && HEX.test(custom.surface || "") ? custom.surface : "#ffffff",
    };
}
