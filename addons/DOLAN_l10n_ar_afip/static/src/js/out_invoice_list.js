/** @odoo-module **/

import { registry } from "@web/core/registry";
import { accountMoveUploadListView } from "@account/views/account_move_list/account_move_list_view";
import { AccountMoveListController } from "@account/views/account_move_list/account_move_list_controller";

class DolanOutInvoiceListController extends AccountMoveListController {
    setup() {
        super.setup();
        if (this.props.context.default_move_type === "out_invoice") {
            this.showUploadButton = false;
        }
    }
}

registry.category("views").add("dolan_out_invoice_tree", {
    ...accountMoveUploadListView,
    Controller: DolanOutInvoiceListController,
    buttonTemplate: "DOLANl10nAr.DolanOutInvoiceListButtons",
});
