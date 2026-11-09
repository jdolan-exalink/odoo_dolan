/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { DOLAN_UI_PALETTES, resolvePaletteColors } from "./dolan_palettes";
import { appIconTileStyle, iconStyleUsesMask, resolveIconAsset } from "./dolan_icon_registry";

const PREVIEW_ICON_APPS = ["app.invoicing", "app.sales", "app.inventory", "app.whatsapp"];

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
        if (this.isIconStyle) return ({ odoo_original: "▦", fluent_3d_classic: "◆", mosaic: "▣", mosaic_brand: "▣", outline: "◇" })[value] || "◇";
        if (["dolan_ui_density", "density"].includes(this.props.name)) return value === "compact" ? "☷" : "▤";
        if (["dolan_ui_icon_scale", "icon_scale"].includes(this.props.name)) return value === "compact" ? "▪" : value === "large" ? "▣" : "▦";
        if (["dolan_ui_visual_effect", "visual_effect"].includes(this.props.name)) return value === "glass" ? "◈" : value === "soft" ? "◉" : "□";
        return ({ light: "☼", dark: "☾", system: "◐", contrast: "◉" })[value] || "◐";
    }

    profileDescription(value) {
        const aliases = { enterprise_classic: "odoo_classic", graphite: "dolan_fluent", glass: "dolan_liquid", minimal: "dolan_minimal" };
        const profile = ({
            odoo_classic: "Lo conocido de Odoo: plano, borde fino y esquinas chicas.",
            dolan_fluent: "Tarjetas elevadas con sombra media y esquinas medias.",
            dolan_liquid: "Paneles translúcidos sobre un fondo en degradado.",
            dolan_material: "Botones grandes tipo píldora y superficies con color.",
            dolan_minimal: "Plano y denso, sin sombras, para administración.",
        })[aliases[value] || value];
        return profile || "Perfil visual";
    }

    iconSamples(style) {
        if (style === "odoo_original") {
            return ["/account/static/description/icon.png", "/sale/static/description/icon.png", "/stock/static/description/icon.png"]
                .map((src) => ({ key: src, src }));
        }
        const assignments = window.dolanUiIconAssignments || {};
        return PREVIEW_ICON_APPS.map((semanticId) => {
            const fallback = `/DOLAN_theme/static/src/lib/${({ fluent_3d_classic: "fluent_3d", mosaic: "fluent_filled", mosaic_brand: "fluent_filled", outline: "fluent_regular" })[style] || "fluent_filled"}/${semanticId.replace("app.", "")}.${style === "fluent_3d_classic" ? "png" : "svg"}`;
            const src = resolveIconAsset(semanticId, style, assignments) || fallback;
            return { key: semanticId, src, mask: iconStyleUsesMask(style), style: appIconTileStyle(semanticId, style, src) };
        });
    }

    get paletteCustomColors() {
        const data = this.props.record.data;
        return {
            primary: data.dolan_ui_custom_primary, secondary: data.dolan_ui_custom_secondary,
            background: data.dolan_ui_custom_background, surface: data.dolan_ui_custom_surface,
        };
    }

    get paletteCompanyColors() {
        const data = this.props.record.data;
        return { primary: data.dolan_ui_primary_color, secondary: data.dolan_ui_secondary_color };
    }

    paletteHint(value) {
        if (value === "company") return "Colores del logo";
        return DOLAN_UI_PALETTES.find((item) => item.id === value)?.hint || "";
    }

    palettePreview(value) {
        const options = { company: this.paletteCompanyColors, custom: this.paletteCustomColors };
        const light = resolvePaletteColors(value, { ...options, dark: false });
        const dark = resolvePaletteColors(value, { ...options, dark: true });
        const half = (colors, text) => `--pv-nav:${colors.navbar};--pv-canvas:${colors.canvas};--pv-surface:${colors.surface};--pv-primary:${colors.primary};--pv-secondary:${colors.secondary};--pv-text:${text}`;
        return { light: half(light, "#1b2230"), dark: half(dark, "#ffffff") };
    }

    colorStyle(value) {
        const colors = resolvePaletteColors(value, { company: this.paletteCompanyColors, custom: this.paletteCustomColors });
        return `--choice-primary:${colors.primary};--choice-secondary:${colors.secondary}`;
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
