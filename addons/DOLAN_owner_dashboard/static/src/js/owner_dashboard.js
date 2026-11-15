/** @odoo-module **/

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Tablero del dueño: caja y bancos, deuda vencida, pagos de la semana, ventas y
 * margen del mes y alertas en una sola pantalla. Los datos salen de la contabilidad
 * (dolan.owner.dashboard.get_data); cada bloque abre su pantalla de detalle.
 */
export class DolanOwnerDashboard extends Component {
    static template = "DOLAN_owner_dashboard.Dashboard";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, error: false, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("dolan.owner.dashboard", "get_data", []);
            this.state.error = false;
        } catch {
            this.state.error = true;
        }
        this.state.loading = false;
    }

    open(xmlid) {
        if (xmlid) {
            this.action.doAction(xmlid);
        }
    }

    changeClass(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return value >= 0 ? "text-success" : "text-danger";
    }
}

registry.category("actions").add("dolan_owner_dashboard", DolanOwnerDashboard);
