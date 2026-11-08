/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const PALETTE_COLORS = {
    dolan: ["#7938d2", "#017e84"],
    ocean: ["#0878b9", "#16b8c9"],
    forest: ["#287271", "#70a288"],
    sunset: ["#d9603b", "#e6a23c"],
    violet: ["#5f3b9c", "#d16bd3"],
    graphite: ["#506477", "#42a5b5"],
    emerald: ["#087f68", "#48b27e"],
    custom: ["#714b67", "#017e84"],
    company: ["#714b67", "#017e84"],
};

export class DolanAppearanceChoice extends Component {
    static template = "DOLAN_theme.DolanAppearanceChoice";
    props = useProps({ ...standardFieldProps });

    get choices() {
        const choices = this.props.record.fields[this.props.name]?.selection || [];
        const hiddenCompatibility = new Set(["legacy", "enterprise_classic", "graphite", "glass", "minimal", "liquid_glass_dark", "liquid_glass_light"]);
        return this.isAppearanceProfile ? choices.filter(([value]) => !hiddenCompatibility.has(value)) : choices;
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get isPalette() {
        return ["dolan_ui_palette", "palette"].includes(this.props.name);
    }

    get isAppearanceProfile() {
        return ["dolan_ui_appearance_profile", "appearance_profile"].includes(this.props.name);
    }

    get isIconStyle() {
        return ["dolan_ui_icon_style", "icon_style"].includes(this.props.name);
    }

    get isMode() {
        return ["dolan_ui_theme_mode", "theme_mode"].includes(this.props.name);
    }

    get isTileChoice() {
        return ["dolan_ui_density", "dolan_ui_icon_scale", "dolan_ui_visual_effect", "dolan_ui_icon_style", "icon_scale", "visual_effect", "icon_style"].includes(this.props.name);
    }

    choiceClass(value) {
        return `${this.isIconStyle ? "o_dolan_settings_icon_choice " : ""}is-choice-${String(value).replaceAll("_", "-")}`;
    }

    choiceGlyph(value) {
        if (this.isIconStyle) return ({ odoo_original: "▦", fluent_3d_classic: "🌈", fluent_flat_modern: "▰", fluent_filled_pro: "⬟", fluent_outline_color: "◇", tabler: "⌘" })[value] || "◇";
        if (["dolan_ui_density", "density"].includes(this.props.name)) return value === "compact" ? "☷" : "▤";
        if (["dolan_ui_icon_scale", "icon_scale"].includes(this.props.name)) return value === "compact" ? "▪" : value === "large" ? "▣" : "▦";
        if (["dolan_ui_visual_effect", "visual_effect"].includes(this.props.name)) return value === "glass" ? "◈" : value === "soft" ? "◉" : "□";
        return ({ light: "☼", dark: "☾", system: "◐", contrast: "◉" })[value] || "◐";
    }

    profileDescription(value) {
        const aliases = { enterprise_classic: "odoo_classic", graphite: "dolan_fluent", glass: "dolan_liquid", minimal: "dolan_minimal" };
        const profile = ({
            odoo_classic: "La experiencia familiar de Odoo, clara y equilibrada.",
            dolan_fluent: "Capas sutiles y navegación de escritorio.",
            dolan_liquid: "Transparencia limitada a navegación y paneles.",
            dolan_material: "Superficies tonales y controles cómodos al tacto.",
            dolan_minimal: "Interfaz plana y compacta para administración.",
        })[aliases[value] || value];
        return profile || "Perfil visual";
    }

    iconSamples(style) {
        const folders = {
            odoo_original: ["/account/static/description/icon.png", "/sale/static/description/icon.png", "/stock/static/description/icon.png"],
            fluent_3d_classic: ["fluent_3d/invoicing.png", "fluent_3d/sales.png", "fluent_3d/whatsapp.png"],
            fluent_flat_modern: ["fluent_flat/invoicing.svg", "fluent_flat/sales.svg", "fluent_flat/whatsapp.svg"],
            fluent_filled_pro: ["fluent_filled/invoicing.svg", "fluent_filled/sales.svg", "fluent_filled/whatsapp.svg"],
            fluent_outline_color: ["fluent_regular/invoicing.svg", "fluent_regular/sales.svg", "fluent_regular/whatsapp.svg"],
            tabler: ["tabler/invoice.svg", "tabler/chart-line.svg", "tabler/whatsapp_brand.svg"],
        };
        return (folders[style] || folders.odoo_original).map((path) => path.startsWith("/") ? path : `/DOLAN_theme/static/src/lib/${path}`);
    }

    colorStyle(value) {
        const customPrimary = this.props.record.data.dolan_ui_primary_color;
        const customSecondary = this.props.record.data.dolan_ui_secondary_color;
        const primaryColor = /^#[0-9a-f]{6}$/i.test(customPrimary || "") ? customPrimary : null;
        const secondaryColor = /^#[0-9a-f]{6}$/i.test(customSecondary || "") ? customSecondary : null;
        const [defaultPrimary, defaultSecondary] = PALETTE_COLORS[value] || PALETTE_COLORS.dolan;
        const primary = ["company", "custom"].includes(value) ? (primaryColor || defaultPrimary) : defaultPrimary;
        const secondary = ["company", "custom"].includes(value) ? (secondaryColor || defaultSecondary) : defaultSecondary;
        return `--choice-primary:${primary};--choice-secondary:${secondary}`;
    }

    themeGlyph(value) {
        return ({ light: "☼", dark: "☾", system: "◐", contrast: "◉", odoo_classic: "O", dolan_fluent: "F", dolan_liquid: "L", dolan_material: "M", dolan_minimal: "▤" })[value] || "◐";
    }

    async select(value) {
        if (!this.props.readonly && value !== this.value) {
            await this.props.record.update({ [this.props.name]: value });
        }
    }
}

registry.category("fields").add("dolan_appearance_choice", {
    component: DolanAppearanceChoice,
    supportedTypes: ["selection"],
});
