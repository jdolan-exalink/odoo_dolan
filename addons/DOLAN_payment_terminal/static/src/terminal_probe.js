/** @odoo-module **/
import { Component, onMounted, onWillDestroy, proxy, useProps } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { standardActionServiceProps } from '@web/webclient/actions/action_plugin';
import { useService } from '@web/core/utils/hooks';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

export class TerminalProbe extends Component {
    static template = 'DOLAN_payment_terminal.TerminalProbe';
    props = useProps({ ...standardActionServiceProps });
    setup() {
        this.state = proxy({ status: 'Sin iniciar', detail: '', connection: 'idle', pairing: 'idle', pairingCode: '', paymentBusy: false });
        this.orm = useService('orm');
        this.authToken = this.props.action.params.auth_token || null;
        this.operation = null;
        this.paymentTimer = null;
        this.leaseTimer = null;
        this.leaseSession = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, '0')).join('');
        this.socket = null;
        this.timer = null;
        this.pairTimer = null;
        onMounted(() => { if (this.props.action.params.auto_connect) this.test(); });
        onWillDestroy(() => { if (this.operation) this.reportResult('uncertain'); this.close(); });
    }
    close() {
        clearTimeout(this.timer);
        clearTimeout(this.pairTimer);
        this.clearLease();
        if (this.socket) {
            this.socket.onopen = this.socket.onerror = this.socket.onclose = this.socket.onmessage = null;
            this.socket.close();
            this.socket = null;
        }
    }
    test() {
        this.close();
        const { host, port } = this.props.action.params;
        this.state.status = 'Conectando';
        this.state.connection = 'connecting';
        this.state.pairing = 'idle';
        this.state.pairingCode = '';
        this.state.detail = 'El navegador debe poder acceder a la red local y confiar en el certificado de Clover.';
        try {
            const socket = this.socket = new WebSocket(`wss://${host}:${port}/remote_pay`);
            socket.onopen = () => {
                this.state.status = 'Conexión de red establecida';
                this.state.connection = 'connected';
                this.state.detail = 'La conexión WSS está abierta en este navegador. Todavía no se comprobó el emparejamiento ni se puede cobrar.';
                clearTimeout(this.timer);
                if (this.authToken) {
                    this.state.detail = 'Conexión abierta. Recuperando el vínculo guardado con Clover...';
                    this.pair();
                }
            };
            socket.onmessage = (event) => this.onMessage(event);
            socket.onerror = () => {
                this.state.status = 'No se pudo conectar';
                this.state.connection = 'disconnected';
                this.state.detail = 'Revisá la IP, la red, Pay Display y el certificado. El navegador no informa la causa exacta.';
            };
            socket.onclose = () => {
                this.clearLease();
                if (this.state.connection === 'connected' || this.state.connection === 'connecting') {
                    if (this.operation) this.reportResult('uncertain');
                    this.state.status = 'Conexión cerrada';
                    this.state.connection = 'disconnected';
                    this.state.pairing = 'idle';
                    this.state.detail = 'Volvé a probar la conexión desde esta PC.';
                }
            };
            this.timer = setTimeout(() => {
                if (this.state.status === 'Conectando') {
                    this.state.status = 'Tiempo de espera agotado';
                    this.state.connection = 'disconnected';
                    this.close();
                }
            }, 10000);
        } catch (_error) {
            this.state.status = 'No se pudo iniciar la conexión';
            this.state.connection = 'disconnected';
            this.state.detail = 'Revisá los permisos del navegador y la configuración de la terminal.';
        }
    }
    pair() {
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN || this.state.pairing === 'pending') return;
        const { terminal_id, remote_app_id, host } = this.props.action.params;
        const key = `dolan-clover-device-${terminal_id}-${host}`;
        let serial = localStorage.getItem(key);
        if (!serial) {
            const bytes = new Uint8Array(10);
            crypto.getRandomValues(bytes);
            serial = 'OD-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
            localStorage.setItem(key, serial);
        }
        const payload = { method: 'PAIRING_REQUEST', serialNumber: serial, name: 'DOLAN Odoo' };
        if (this.authToken) payload.authenticationToken = this.authToken;
        this.state.pairing = 'pending';
        this.state.pairingCode = '';
        this.state.detail = 'Esperando la respuesta de la terminal. Si solicita un PIN de gerente, ingresalo en el equipo.';
        this.pairTimer = setTimeout(() => {
            if (this.state.pairing === 'pending') {
                this.state.pairing = 'error';
                this.state.detail = 'No llegó una confirmación de emparejamiento. Revisá la terminal y volvé a intentar.';
            }
        }, 120000);
        try {
            this.socket.send(JSON.stringify({ method: 'PAIRING_REQUEST', payload: JSON.stringify(payload),
                remoteApplicationID: remote_app_id, remoteSourceSDK: 'DOLAN-Odoo-1.0', version: 1 }));
        } catch (_error) {
            clearTimeout(this.pairTimer);
            this.state.pairing = 'error';
            this.state.detail = 'No se pudo enviar la solicitud de emparejamiento.';
        }
    }
    async onMessage(event) {
        try {
            const message = JSON.parse(event.data);
            const payload = typeof message.payload === 'string' ? JSON.parse(message.payload) : (message.payload || {});
            if (this.operation && message.method === 'FINISH_OK') {
                const payment = typeof payload.payment === 'string' ? JSON.parse(payload.payment) : payload.payment;
                const valid = payment && payment.externalPaymentId === this.operation.external_id &&
                    Number(payment.amount) === 1000 && payment.result === 'SUCCESS' && payment.id;
                this.reportResult(valid ? 'success' : 'uncertain', valid ? payment.id : false);
                return;
            }
            if (this.operation && message.method === 'FINISH_CANCEL') {
                this.reportResult('cancelled');
                return;
            }
            if (this.state.pairing !== 'pending') return;
            if (message.method === 'PAIRING_CODE') {
                this.state.pairingCode = String(payload.pairingCode || payload.code || '');
                this.state.detail = this.state.pairingCode ? 'Ingresá este código en la terminal.' : 'La terminal no proporcionó un código de emparejamiento.';
            } else if (message.method === 'PAIRING_RESPONSE') {
                if (payload.pairingState === 'PAIRED' || payload.pairingState === 'INITIAL') {
                    clearTimeout(this.pairTimer);
                    this.authToken = payload.authenticationToken || this.authToken;
                    this.state.pairing = 'paired';
                    this.startLease();
                    this.state.pairingCode = '';
                    if (this.authToken) {
                        try {
                            await this.orm.call('dolan.payment.terminal', 'action_store_clover_pairing',
                                [[this.props.action.params.terminal_id], this.authToken]);
                            this.state.detail = 'Vínculo guardado cifrado en Odoo. Al volver a abrir el navegador se reutilizará para reconectar.';
                        } catch (_error) {
                            this.state.detail = 'Conectado por esta sesión, pero no se pudo guardar el vínculo en Odoo. Revisá admin_passwd y los permisos del servidor.';
                        }
                    } else {
                        this.state.detail = 'Clover aceptó la conexión de esta sesión, pero no devolvió un token para conservar el vínculo.';
                    }
                } else if (payload.pairingState === 'AUTHENTICATING') {
                    this.state.detail = 'Esperando la autenticación en la terminal.';
                } else if (payload.pairingState === 'FAILED') {
                    clearTimeout(this.pairTimer);
                    this.state.pairing = 'error';
                    this.state.detail = 'La terminal rechazó el emparejamiento. Revisá el identificador de aplicación y la configuración del equipo.';
                }
            }
        } catch (_error) {
            this.state.detail = 'La terminal envió una respuesta que no se pudo interpretar.';
        }
    }
    leaseKey() {
        return `${this.props.action.params.lease_prefix}${this.leaseSession}`;
    }
    startLease() {
        this.clearLease();
        const renew = () => localStorage.setItem(this.leaseKey(), String(Date.now() + 12000));
        renew();
        this.leaseTimer = setInterval(renew, 4000);
    }
    clearLease() {
        clearInterval(this.leaseTimer);
        if (this.props.action?.params?.terminal_id) localStorage.removeItem(this.leaseKey());
    }
    async testPayment() {
        if (this.state.pairing !== 'paired' || !this.socket || this.socket.readyState !== WebSocket.OPEN || this.operation || this.state.paymentBusy) return;
        this.state.paymentBusy = true;
        this.state.detail = 'Reservando la terminal para la prueba de $10...';
        let operation;
        try {
            operation = await this.orm.call('dolan.payment.terminal', 'action_begin_clover_test', [[this.props.action.params.terminal_id]]);
            this.operation = operation;
            if (!this.socket || this.socket.readyState !== WebSocket.OPEN || this.state.pairing !== 'paired') {
                await this.reportResult('uncertain');
                return;
            }
            const intent = { action: 'com.clover.intent.action.PAY', amount: 1000, tipAmount: 0, taxAmount: 0,
                transactionType: 'PAYMENT', externalPaymentId: operation.external_id,
                allowOfflinePayment: false, approveOfflinePaymentWithoutPrompt: false,
                requiresRemoteConfirmation: true, allowPartialAuth: false,
                transactionSettings: { cloverShouldHandleReceipts: true, disableReceiptSelection: false,
                    tipMode: 'NO_TIP', disableDuplicateCheck: false, autoAcceptPaymentConfirmations: true,
                    autoAcceptSignature: true, cardEntryMethods: 1799 } };
            const payload = { id: operation.external_id, method: 'TX_START', payIntent: intent, order: null, requestInfo: 'SALE' };
            this.socket.send(JSON.stringify({ method: 'TX_START', payload: JSON.stringify(payload),
                remoteApplicationID: this.props.action.params.remote_app_id, remoteSourceSDK: 'DOLAN-Odoo-1.0',
                version: 2, directed: true, packageName: 'com.clover.remote_protocol_broadcast.app' }));
            this.state.detail = 'Cobro de prueba de $10 enviado. Completalo o cancelalo en la terminal.';
            this.paymentTimer = setTimeout(() => { if (this.operation) this.reportResult('uncertain'); }, 180000);
        } catch (_error) {
            if (operation) await this.reportResult('uncertain');
            else this.state.detail = 'No se pudo reservar la terminal. Revisá si hay una operación pendiente.';
            this.state.paymentBusy = false;
        }
    }
    async reportResult(outcome, providerReference = false) {
        const operation = this.operation;
        if (!operation) return;
        this.operation = null;
        clearTimeout(this.paymentTimer);
        this.state.pairing = 'review';
        this.state.detail = 'Resultado en revisión. Consultá la operación antes de intentar otro cobro.';
        try {
            await this.orm.call('dolan.payment.terminal', 'action_report_clover_test',
                [[this.props.action.params.terminal_id], operation.operation_id, outcome, providerReference]);
        } catch (_error) {
            this.state.detail = 'No se pudo guardar el resultado. La operación permanece reservada: revisala antes de reintentar.';
        }
        this.state.paymentBusy = false;
    }
}
registry.category('actions').add('dolan_terminal_probe', TerminalProbe);

class CloverPairStatus extends Component {
    static template = 'DOLAN_payment_terminal.CloverPairStatus';
    props = useProps({ ...standardFieldProps });
    setup() {
        this.state = proxy({ status: 'Sin emparejar', connected: false, linked: false });
        this.refresh = () => {
            const record = this.props.record;
            const provider = record.data.provider;
            const prefix = record.data.clover_status_prefix;
            this.state.connected = provider === 'clover' && Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i))
                .some((key) => key && key.startsWith(prefix) && Number(localStorage.getItem(key)) > Date.now());
            this.state.linked = provider === 'clover' && Boolean(record.data.clover_paired);
            this.state.status = provider === 'clover' ? this.state.linked ? 'Emparejado' : 'Sin emparejar' : 'No aplica';
            this.state.connectionLabel = provider === 'clover'
                ? this.state.connected ? 'Conectado' : this.state.linked ? 'Vínculo guardado' : 'Sin sesión activa'
                : 'Mercado Pago pendiente';
        };
        onMounted(() => { this.refresh(); this.timer = setInterval(this.refresh, 3000); window.addEventListener('storage', this.refresh); });
        onWillDestroy(() => { clearInterval(this.timer); window.removeEventListener('storage', this.refresh); });
    }
}
registry.category('fields').add('dolan_clover_pair_status', { component: CloverPairStatus, supportedTypes: ['char'] });

class TerminalProviderBadge extends Component {
    static template = 'DOLAN_payment_terminal.TerminalProviderBadge';
    props = useProps({ ...standardFieldProps });
}
registry.category('fields').add('dolan_terminal_provider_badge', { component: TerminalProviderBadge, supportedTypes: ['char'] });
