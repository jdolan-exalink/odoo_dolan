/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.dolanPadronNotification = useService("notification");
    },

    async beforeExecuteActionButton(clickParams) {
        const record = this.model?.root;
        if (
            clickParams.name !== "action_l10n_ar_update_from_padron" ||
            this.props.resModel !== "res.partner" ||
            !record?.isNew
        ) {
            return super.beforeExecuteActionButton(...arguments);
        }

        try {
            const result = await this.orm.call(
                "res.partner",
                "action_l10n_ar_lookup_padron_draft",
                [record.data.vat || false],
                { context: record.context }
            );
            if (result.values) {
                const values = { ...result.values };
                if (typeof values.l10n_ar_padron_last_update === "string") {
                    values.l10n_ar_padron_last_update = deserializeDateTime(
                        values.l10n_ar_padron_last_update
                    );
                }
                await record.update(values);
                this.dolanPadronNotification.add(
                    _t("Se completaron los datos disponibles desde el Padrón ARCA."),
                    { title: _t("Padrón ARCA actualizado"), type: "success" }
                );
            } else {
                const message = result.error || _t("ARCA no devolvió datos para este CUIT.");
                await record.update({ l10n_ar_padron_error: message });
                this.dolanPadronNotification.add(message, {
                    title: _t("No se pudo consultar el Padrón ARCA"),
                    type: "danger",
                    sticky: true,
                });
            }
        } catch (error) {
            const message = _t(
                "No se pudo completar la consulta del Padrón. Revisá la conexión e intentá nuevamente."
            );
            await record.update({ l10n_ar_padron_error: message });
            console.error("DOLAN ARCA Padron lookup failed", error);
            this.dolanPadronNotification.add(message, {
                title: _t("No se pudo consultar el Padrón ARCA"),
                type: "danger",
                sticky: true,
            });
        }

        // Returning false prevents FormController's default save-before-button
        // behavior. The lookup updates only this in-memory form draft.
        return false;
    },
});
