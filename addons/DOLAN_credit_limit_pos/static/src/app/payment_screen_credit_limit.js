/**
 * Antes de validar una venta con cobro en cuenta corriente ("pay later"),
 * consulta al servidor si el cliente excede su límite de crédito o lo tiene
 * bloqueado. Un usuario autorizado puede confirmar la excepción; el resto ve
 * el motivo y la venta no se valida. Sin conexión no se bloquea la caja.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    dolanPayLaterAmount() {
        return this.currentOrder.payment_ids
            .filter((line) => line.payment_method_id.type === "pay_later")
            .reduce((total, line) => total + line.amount, 0);
    },

    async dolanCreditAllowed() {
        const partner = this.currentOrder.getPartner();
        const amount = this.dolanPayLaterAmount();
        if (!partner || amount <= 0) {
            return true;
        }
        let result;
        try {
            result = await this.pos.data.call("res.partner", "dolan_pos_check_credit", [
                partner.id,
                amount,
                this.pos.config.id,
            ]);
        } catch (error) {
            console.warn("DOLAN: no se pudo verificar el límite de crédito", error);
            return true;
        }
        if (result.allowed) {
            return true;
        }
        if (result.can_override) {
            return await new Promise((resolve) => {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Límite de crédito excedido"),
                    body: result.message + "\n\n" + _t("¿Autorizás la venta en cuenta corriente igual?"),
                    confirmLabel: _t("Autorizar"),
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                });
            });
        }
        this.dialog.add(AlertDialog, {
            title: _t("Límite de crédito excedido"),
            body: result.message + "\n\n" + _t("Cobrá con otro medio o pedí autorización a un supervisor."),
        });
        return false;
    },

    async onClickValidate(args = {}) {
        if (!(await this.dolanCreditAllowed())) {
            return;
        }
        return await super.onClickValidate(...arguments);
    },
});
