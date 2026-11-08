/** @odoo-module **/

import { Component, onMounted, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Odoo-supported home action for DOLAN deployments. It keeps the user on the
 * launcher without making Discuss (or another root menu) the implicit default.
 */
export class DolanHomeAction extends Component {
    static template = "DOLAN_theme.DolanHomeAction";

    setup() {
        onMounted(() => {
            document.body.classList.add("o_dolan_home_action_active");
            this.env.bus.trigger("DOLAN:OPEN_LAUNCHER");
        });
        onWillDestroy(() => document.body.classList.remove("o_dolan_home_action_active"));
    }
}

registry.category("actions").add("dolan_home", DolanHomeAction);
