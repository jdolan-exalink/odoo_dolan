/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/** Botón «Sitio web» de la barra superior: abre la web en la misma pestaña. */
export class DolanWebsiteSystray extends Component {
    static template = "DOLAN_website_nav.WebsiteSystray";

    openWebsite() {
        window.location.href = "/";
    }
}

registry.category("systray").add("DOLAN_website_nav.WebsiteSystray", { Component: DolanWebsiteSystray }, { sequence: 13 });
