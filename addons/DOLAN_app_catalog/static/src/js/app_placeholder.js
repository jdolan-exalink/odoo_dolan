/** @odoo-module **/

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STATE_HELP = {
    en_desarrollo: "Esta app está en desarrollo. Todavía no registra datos ni hace operaciones.",
    planificado: "Esta app está planificada. Todavía no registra datos ni hace operaciones.",
    disponible: "El módulo que la implementa existe pero no está instalado en esta base. Un administrador puede instalarlo desde Aplicaciones.",
};

/**
 * Pantalla informativa de una app del catálogo que todavía no se puede usar.
 * No tiene botones de operaciones: solo describe la app y su estado.
 * El servidor valida que el usuario pueda ver la app antes de devolver datos.
 */
export class DolanAppPlaceholder extends Component {
    static template = "DOLAN_app_catalog.AppPlaceholder";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, error: false });
        onWillStart(async () => {
            const key = this.props.action?.params?.key;
            try {
                this.state.data = await this.orm.call("dolan.app.catalog.entry", "get_placeholder", [key]);
            } catch {
                this.state.error = true;
            }
        });
    }

    get help() {
        return STATE_HELP[this.state.data?.state] || "";
    }

    goHome() {
        this.env.bus.trigger("DOLAN:OPEN_LAUNCHER");
    }

    openApps() {
        this.action.doAction("base.open_module_tree", {
            additionalContext: { search_default_name: this.state.data.module },
        });
    }
}

registry.category("actions").add("dolan_app_catalog_placeholder", DolanAppPlaceholder);
