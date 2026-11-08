/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import { AlertDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { PaymentInterface } from '@point_of_sale/app/utils/payment/payment_interface';
import { registry } from '@web/core/registry';

const FINAL = new Set(['approved', 'rejected', 'cancelled']);

/** Clover Pay Display POS interface. The persisted operation UUID is the one-shot TX_START guard. */
export class DolanCloverPayment extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.socket = null;
        this.operation = null;
        this.resolver = null;
        this.pollTimer = null;
        this.dispatched = false;
        this.completed = false;
        this.connectionFailureHandled = false;
    }

    async sendPaymentRequest(line) {
        const method = line.payment_method_id;
        const terminalId = method.dolan_terminal_id;
        if (!terminalId || line.amount <= 0) {
            this._message(_t('Asigná una terminal Clover activa y verificá que el importe sea mayor que cero.'), _t('Configuración incompleta'));
            return false;
        }
        const externalId = `DOLAN-${line.uuid}`.slice(0, 64);
        const orderUuid = line.pos_order_id?.uuid || this.pos.getOrder()?.uuid;
        if (!orderUuid) {
            this._message(_t('No se pudo identificar el pedido del POS. No se inició el cobro.'), _t('Pedido no disponible'));
            return false;
        }
        line.ticket = externalId;
        let operation;
        try {
            operation = await this.orm.call('dolan.payment.terminal', 'action_begin_pos_payment', [
                [terminalId], externalId, orderUuid, line.amount, line.currency?.name,
            ]);
        } catch (error) {
            this._message(error?.data?.message || error?.message || _t('No se pudo reservar la terminal.'), _t('No se pudo reservar la terminal'));
            return false;
        }
        this.operation = { ...operation, terminalId, externalId, amountCents: Math.round(line.amount * 100), line };
        if (operation.state === 'approved') {
            line.transaction_id = operation.provider_reference || externalId;
            line.setPaymentStatus('done');
            return true;
        }
        if (['rejected', 'cancelled'].includes(operation.state)) {
            this._message(_t('Este intento ya terminó como %s. Creá una nueva línea solo después de verificar el registro del proveedor.', operation.state), _t('Intento finalizado'));
            return false;
        }
        if (operation.state !== 'prepared' || !operation.dispatch_allowed) {
            // An earlier attempt may have reached the terminal. Reconcile it, never send another TX_START.
            line.setPaymentStatus('waitingCard');
            return new Promise((resolve) => { this.resolver = resolve; this._poll(); });
        }

        line.setPaymentStatus('waitingCapture');
        return new Promise((resolve) => {
            this.resolver = resolve;
            this._connectAndPay();
        });
    }

    async _connectAndPay() {
        try {
            const terminal = await this.orm.call('dolan.payment.terminal', 'action_get_pos_clover_config', [[this.operation.terminalId]]);
            this.terminal = terminal;
            this.socket = new WebSocket(`wss://${terminal.host}:${terminal.port}/remote_pay`);
            this.socket.onmessage = (event) => this._onMessage(event);
            this.socket.onerror = () => this._connectionFailed();
            this.socket.onclose = () => { if (this.dispatched && !this.completed) this._report('uncertain'); };
            this.socket.onopen = () => this._pair();
            this.connectionTimer = setTimeout(() => this._connectionFailed(), 15000);
        } catch (error) {
            this._message(error?.data?.message || error?.message || _t('No se pudo conectar con Clover.'), _t('No se pudo conectar con Clover'));
            await this._report('cancelled');
            this.completed = true;
            this.operation?.line.setPaymentStatus('retry');
            this.resolver?.(false);
            this.resolver = null;
        }
    }

    _pair() {
        const key = `dolan-clover-device-${this.operation.terminalId}-${this.terminal.host}`;
        let serial = localStorage.getItem(key);
        if (!serial) {
            const bytes = new Uint8Array(10);
            crypto.getRandomValues(bytes);
            serial = `OD-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
            localStorage.setItem(key, serial);
        }
        this.pairingTimer = setTimeout(() => this._connectionFailed(), 30000);
        this.socket.send(JSON.stringify({ method: 'PAIRING_REQUEST',
            payload: JSON.stringify({ method: 'PAIRING_REQUEST', serialNumber: serial,
                name: 'DOLAN Odoo POS', authenticationToken: this.terminal.auth_token }),
            remoteApplicationID: this.terminal.remote_app_id,
            remoteSourceSDK: 'DOLAN-Odoo-1.0', version: 1 }));
    }

    async _onMessage(event) {
        let message;
        let payload;
        try {
            message = JSON.parse(event.data);
            payload = typeof message.payload === 'string' ? JSON.parse(message.payload) : (message.payload || {});
        } catch (_error) { return; }
        if (message.method === 'PAIRING_RESPONSE') {
            if (payload.pairingState === 'PAIRED' || payload.pairingState === 'INITIAL') {
                clearTimeout(this.pairingTimer);
                try {
                    await this._dispatch();
                } catch (_error) {
                    await this._connectionFailed();
                }
            } else if (payload.pairingState === 'FAILED') {
                clearTimeout(this.pairingTimer);
                await this._report('cancelled');
                this._message(_t('Clover rechazó el vínculo. Emparejá nuevamente desde la configuración de terminales.'), _t('Emparejamiento fallido'));
                this.completed = true;
                this.operation?.line.setPaymentStatus('retry');
                this.resolver?.(false);
                this.resolver = null;
            }
            return;
        }
        if (!this.operation || this.completed) return;
        if (message.method === 'FINISH_OK') {
            let payment;
            try {
                payment = typeof payload.payment === 'string' ? JSON.parse(payload.payment) : payload.payment;
            } catch (_error) {
                await this._report('uncertain');
                return;
            }
            const valid = payment && payment.externalPaymentId === this.operation.externalId &&
                Number(payment.amount) === this.operation.amountCents && payment.result === 'SUCCESS' && payment.id;
            if (!valid) {
                await this._report('uncertain', payment?.id, payment?.externalPaymentId, payment?.amount);
                return;
            }
            const result = await this._report('approved', payment.id, payment.externalPaymentId, payment.amount);
            if (result?.state === 'approved' && result.verified) {
                this.operation.line.transaction_id = payment.id;
                this.operation.line.setPaymentStatus('done');
                this.completed = true;
                this.resolver?.(true);
                this.resolver = null;
            } else {
                this._message(_t('Clover indicó aprobación, pero el servidor no pudo verificarla. La operación quedó en revisión.'), _t('Conciliación requerida'));
                this._poll();
            }
        } else if (message.method === 'FINISH_CANCEL') {
            await this._report('cancelled');
            this.operation.line.setPaymentStatus('retry');
            this.completed = true;
            this.resolver?.(false);
            this.resolver = null;
        }
    }

    async _dispatch() {
        const mark = await this.orm.call('dolan.payment.terminal', 'action_mark_pos_payment_dispatching', [
            [this.operation.terminalId], this.operation.operation_id,
        ]);
        if (!mark.dispatch_allowed) {
            this._poll();
            return;
        }
        const line = this.operation.line;
        const intent = { action: 'com.clover.intent.action.PAY', amount: this.operation.amountCents,
            tipAmount: 0, taxAmount: 0, transactionType: 'PAYMENT',
            externalPaymentId: this.operation.externalId, allowOfflinePayment: false,
            approveOfflinePaymentWithoutPrompt: false, requiresRemoteConfirmation: true,
            allowPartialAuth: false,
            transactionSettings: { cloverShouldHandleReceipts: true, disableReceiptSelection: false,
                tipMode: 'NO_TIP', disableDuplicateCheck: false, autoAcceptPaymentConfirmations: true,
                autoAcceptSignature: true, cardEntryMethods: 1799 } };
        const payload = { id: this.operation.externalId, method: 'TX_START', payIntent: intent, order: null, requestInfo: 'SALE' };
        // Once send() is attempted, any lost response is uncertain; retries only poll this operation.
        this.dispatched = true;
        line.setPaymentStatus('waitingCard');
        this.socket.send(JSON.stringify({ method: 'TX_START', payload: JSON.stringify(payload),
            remoteApplicationID: this.terminal.remote_app_id, remoteSourceSDK: 'DOLAN-Odoo-1.0',
            version: 2, directed: true, packageName: 'com.clover.remote_protocol_broadcast.app' }));
        this._poll();
    }

    async _report(outcome, providerReference = false, responseExternalId = false, amountCents = 0) {
        if (!this.operation) return null;
        try {
            return await this.orm.call('dolan.payment.terminal', 'action_report_pos_payment', [
                [this.operation.terminalId], this.operation.operation_id, outcome,
                providerReference, responseExternalId, amountCents,
            ]);
        } catch (_error) {
            this._message(_t('No se pudo guardar la respuesta. La terminal sigue reservada; no repitas el cobro.'), _t('Estado incierto'));
            return null;
        }
    }

    async _poll() {
        if (!this.operation || this.completed || this.pollInFlight) return;
        this.pollInFlight = true;
        try {
            const state = await this.orm.call('dolan.payment.terminal', 'action_get_pos_payment_state', [
                [this.operation.terminalId], this.operation.operation_id,
            ]);
            if (state.state === 'approved') {
                this.operation.line.transaction_id = state.provider_reference || this.operation.externalId;
                this.operation.line.setPaymentStatus('done');
                this.completed = true;
                this.resolver?.(true);
                this.resolver = null;
                return;
            }
            if (FINAL.has(state.state)) {
                this.operation.line.setPaymentStatus('retry');
                this.completed = true;
                this.resolver?.(false);
                this.resolver = null;
                return;
            }
            // If Odoo was unreachable when the socket dropped, recover the dispatching
            // row into a supervisor-review state once RPC access returns.
            if (this.dispatched && state.state === 'dispatching') {
                await this._report('uncertain');
            }
        } catch (_error) {
            // Leave the line in waiting state while the backend reconciles it.
        } finally {
            this.pollInFlight = false;
        }
        this.pollTimer = setTimeout(() => this._poll(), 3000);
    }

    async _connectionFailed() {
        if (this.connectionFailureHandled || this.completed) return;
        this.connectionFailureHandled = true;
        clearTimeout(this.connectionTimer);
        clearTimeout(this.pairingTimer);
        if (!this.dispatched) {
            await this._report('cancelled');
            this.completed = true;
            this.operation?.line.setPaymentStatus('retry');
            this.resolver?.(false);
            this.resolver = null;
            this._message(_t('No se pudo establecer la conexión con Clover; no se envió el cobro.'), _t('Error de conexión'));
        } else {
            await this._report('uncertain');
            this._message(_t('La conexión se cortó durante el cobro. DOLAN conserva el bloqueo y consultará la misma operación; no vuelvas a cobrar.'), _t('Conciliación requerida'));
            this._poll();
        }
    }

    async sendPaymentCancel() {
        // Clover cancellation is made on the terminal; removing the POS line is unsafe.
        this._message(_t('Cancelá o completá el cobro desde Clover. La línea no se libera hasta recibir el resultado.'), _t('Cobro en curso'));
        return false;
    }

    close() {
        if (this.dispatched && !this.completed) this._report('uncertain');
        clearTimeout(this.pollTimer);
        clearTimeout(this.connectionTimer);
        clearTimeout(this.pairingTimer);
        this.socket?.close();
        this.socket = null;
    }

    _message(body, title) { this.dialog.add(AlertDialog, { title, body: String(body || '') }); }
}

registry.category('pos_payment_providers').add('dolan_clover', DolanCloverPayment);
