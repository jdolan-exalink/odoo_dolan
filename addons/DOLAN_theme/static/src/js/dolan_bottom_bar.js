/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DolanBottomBar extends Component {
    static template = "DOLAN_theme.BottomBar";

    setup() {
        this.actionService = useService("action");
    }

    onHomeClick() {
        this.env.bus.trigger("DOLAN:CLOSE_AI_CHAT");
        this.env.bus.trigger("DOLAN:OPEN_APP_DRAWER");
    }

    onSearchClick() {
        this.env.bus.trigger("DOLAN:CLOSE_AI_CHAT");
        this.env.bus.trigger("DOLAN:OPEN_APP_SEARCH");
    }

    onAiClick() {
        this.env.bus.trigger("DOLAN:TOGGLE_AI_CHAT");
    }

    onMessagesClick() {
        this.env.bus.trigger("DOLAN:CLOSE_AI_CHAT");
        this.actionService.doAction("mail.action_discuss");
    }

    onQuickActionsClick() {
        this.env.bus.trigger("DOLAN:CLOSE_AI_CHAT");
        this.env.bus.trigger("DOLAN:OPEN_QUICK_ACTIONS");
    }
}

registry.category("main_components").add("DolanBottomBar", {
    Component: DolanBottomBar,
});
