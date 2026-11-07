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
    company: ["#714b67", "#017e84"],
};

export class DolanAppearanceChoice extends Component {
    static template = "DOLAN_theme.DolanAppearanceChoice";
    props = useProps({ ...standardFieldProps });

    get choices() {
        return this.props.record.fields[this.props.name]?.selection || [];
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get isPalette() {
        return this.props.name === "dolan_ui_palette";
    }

    colorStyle(value) {
        const customPrimary = this.props.record.data.dolan_ui_primary_color;
        const customSecondary = this.props.record.data.dolan_ui_secondary_color;
        const primaryColor = /^#[0-9a-f]{6}$/i.test(customPrimary || "") ? customPrimary : null;
        const secondaryColor = /^#[0-9a-f]{6}$/i.test(customSecondary || "") ? customSecondary : null;
        const [defaultPrimary, defaultSecondary] = PALETTE_COLORS[value] || PALETTE_COLORS.dolan;
        const primary = value === "company" ? (primaryColor || defaultPrimary) : defaultPrimary;
        const secondary = value === "company" ? (secondaryColor || defaultSecondary) : defaultSecondary;
        return `--choice-primary:${primary};--choice-secondary:${secondary}`;
    }

    themeGlyph(value) {
        return ({ light: "☼", dark: "☾", system: "◐", contrast: "◉" })[value] || "◐";
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
