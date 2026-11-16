/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Botón «?» de la barra superior: abre la ayuda de la app donde está el usuario. */
export class DolanHelpSystray extends Component {
    static template = "DOLAN_help.HelpSystray";

    setup() {
        this.action = useService("action");
        this.menu = useService("menu");
        this.orm = useService("orm");
    }

    async openHelp() {
        const app = this.menu.getCurrentApp();
        const controller = this.action.currentController;
        const actionXmlid = controller?.action?.xml_id || controller?.action?.xmlid || null;
        let ref = "";
        if (controller?.action?.tag !== "dolan_help_center" && (app || actionXmlid)) {
            try {
                const apps = await this.orm.call("dolan.help.center", "get_context_apps", [], {
                    menu_id: app?.id || null,
                    action_xmlid: actionXmlid,
                });
                if (apps.length) {
                    ref = `app:${apps[0].key}`;
                }
            } catch {
                ref = "";
            }
        }
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "dolan_help_center",
            name: "Ayuda",
            params: { ref },
        });
    }
}

registry.category("systray").add("DOLAN_help.HelpSystray", { Component: DolanHelpSystray }, { sequence: 14 });
