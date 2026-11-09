/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import { AlertDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { PaymentInterface } from '@point_of_sale/app/utils/payment/payment_interface';
import { registry } from '@web/core/registry';

const POLL_MS = 2000;
const TERMINAL_STATES = new Set(['processed', 'canceled', 'cancelled', 'expired', 'rejected', 'failed']);

/** Mercado Pago dynamic QR. Network uncertainty never releases the payment line. */
export class DolanMercadoPagoQR extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.pollTimer = null;
        this.resolver = null;
        this.order = null;
        this.networkWarningShown = false;
    }

    async sendPaymentRequest(line) {
        if (line.amount <= 0) {
            this._message(_t('El importe debe ser mayor que cero.'), _t('Importe no válido'));
            return false;
        }
        // Stable per payment line; the backend derives Mercado Pago's idempotency key from it.
        const externalReference = `DOLANQR-${line.uuid}`.slice(0, 64);
        const orderUuid = line.pos_order_id?.uuid || this.pos.getOrder()?.uuid;
        if (!orderUuid) {
            this._message(_t('No se pudo identificar el pedido del POS. No se inició el cobro.'), _t('Pedido no disponible'));
            return false;
        }
        line.ticket = externalReference;
        line.setPaymentStatus('waitingCapture');
        let created;
        try {
            created = await this.callPaymentMethod('action_mp_create_qr_order', [
                [line.payment_method_id.id], line.amount, externalReference, orderUuid, 'Venta POS',
                line.currency?.name,
            ]);
        } catch (error) {
            const isProviderRejection = String(error?.data?.name || '').includes('UserError') ||
                String(error?.data?.name || '').includes('ValidationError');
            if (isProviderRejection) {
                line.setPaymentStatus('retry');
                this._message(error?.data?.message || error?.message || _t('Revisá el token y la configuración del medio de pago.'), _t('Mercado Pago rechazó la configuración o la orden'));
                return false;
            }
            // An RPC timeout can happen after the API request reached Mercado Pago.
            // Keep the line locked and recover using the same external reference.
            line.setPaymentStatus('waitingScan');
            this._message(_t('No se pudo confirmar la creación del QR. La línea queda bloqueada para evitar otro cobro. Consultá la misma referencia y volvé a intentar desde esta línea.'), _t('Estado incierto'));
            return new Promise((resolve) => { this.resolver = resolve; this._poll(line, externalReference, null); });
        }
        if (created?.uncertain) {
            line.setPaymentStatus('waitingScan');
            this._message(_t('Mercado Pago no confirmó si recibió la orden. El sistema consultará la misma referencia antes de permitir otro intento.'), _t('Estado incierto'));
            return new Promise((resolve) => { this.resolver = resolve; this._poll(line, externalReference, null); });
        }
        if (!created?.order_id) {
            line.setPaymentStatus('retry');
            this._message(_t('Mercado Pago no devolvió un identificador de orden. No se marcó el pago como realizado.'), _t('Orden no confirmada'));
            return false;
        }
        this.order = created;
        line.transaction_id = created.order_id;
        if (created.qr_data) {
            line.qr_code = created.qr_data;
        }
        line.setPaymentStatus('waitingScan');
        this._message(_t('Escaneá el QR y esperá la confirmación de Mercado Pago. No cierres ni vuelvas a cobrar mientras la operación esté pendiente.'), _t('Esperando el pago'));
        return new Promise((resolve) => {
            this.resolver = resolve;
            this._poll(line, externalReference, created.order_id);
        });
    }

    async _poll(line, externalReference, orderId) {
        if (this.pollTimer) clearTimeout(this.pollTimer);
        try {
            // If create timed out, a same-key retry safely recovers the order, not a second charge.
            if (!orderId) {
                const recovered = await this.callPaymentMethod('action_mp_create_qr_order', [
                    [line.payment_method_id.id], line.amount, externalReference,
                    line.pos_order_id?.uuid || this.pos.getOrder()?.uuid, 'Venta POS',
                    line.currency?.name,
                ]);
                orderId = recovered?.order_id;
                if (orderId) {
                    this.order = recovered;
                    line.transaction_id = orderId;
                    line.qr_code = recovered.qr_data || line.qr_code;
                }
            }
            if (!orderId) throw new Error('Mercado Pago todavía no devolvió una orden recuperable.');
            const state = await this.callPaymentMethod('action_mp_order_check_status', [
                [line.payment_method_id.id], orderId,
            ]);
            if (state.order_id !== orderId || state.external_reference !== externalReference) {
                throw new Error('La respuesta no corresponde a la referencia de esta venta.');
            }
            const sameAmount = Number.isFinite(Number(state.amount)) && Math.abs(Number(state.amount) - line.amount) < 0.01;
            if (state.status === 'processed' && state.payment_status === 'processed' &&
                state.payment_id && sameAmount) {
                line.transaction_id = orderId;
                line.setPaymentStatus('done');
                this.resolver?.(true);
                this.resolver = null;
                return;
            }
            if (TERMINAL_STATES.has(state.status)) {
                line.setPaymentStatus('retry');
                if (this.resolver) {
                    this._message(_t('Mercado Pago informó que la orden terminó sin un pago aprobado (%s).', state.status), _t('Pago no aprobado'));
                    this.resolver(false);
                    this.resolver = null;
                }
                return;
            }
        } catch (_error) {
            // Preserve the lock in the UI and keep reconciling; never convert a timeout into success/failure.
            if (!this.networkWarningShown) {
                this.networkWarningShown = true;
                this._message(_t('Se perdió la consulta al proveedor. El estado del cobro es incierto: no inicies otro pago. El sistema seguirá consultando esta misma orden.'), _t('Reconectando Mercado Pago'));
            }
        }
        this.pollTimer = setTimeout(() => this._poll(line, externalReference, orderId), POLL_MS);
    }

    async sendPaymentCancel() {
        // The QR may already have been paid. Cancelling the Odoo line would permit a duplicate.
        this._message(_t('No se libera una línea con QR pendiente. Confirmá el estado de la orden en Mercado Pago.'), _t('Conciliación requerida'));
        return false;
    }

    _message(body, title) {
        this.dialog.add(AlertDialog, { title, body });
    }
}

registry.category('pos_payment_providers').add('dolan_mp_qr', DolanMercadoPagoQR);
