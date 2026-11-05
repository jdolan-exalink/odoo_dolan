/** @odoo-module **/

import { Component, onWillStart, proxy, useProps } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { standardActionServiceProps } from '@web/webclient/actions/action_plugin';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';
import { getLNATargetAddressSpace, initLNA } from '@point_of_sale/app/utils/init_lna';

const escapeXml = (value) => String(value || '').replace(/[<>&"']/g, (char) => ({
    '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;',
}[char]));

export class EposPrintTest extends Component {
    static template = 'ePOS_print.EposPrintTest';
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.params = { ...(this.props.action.params || {}) };
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.state = proxy({
            status: this.params.last_test_state === 'ok' ? 'Disponible' : this.params.last_test_state === 'error' ? 'Revisar conexión' : 'Sin probar',
            result: this.params.last_test_state || 'never',
            detail: this.params.last_test_at ? `Última prueba registrada: ${this.params.last_test_at}` : 'La prueba envía una muestra de impresión al equipo.',
            busy: false,
        });
        onWillStart(async () => {
            if (this.params.printer_id) return;
            const match = window.location.pathname.match(/\/action-\d+\/(\d+)(?:\/epos_print_test)?\/?$/);
            const printerId = match ? Number(match[1]) : 0;
            if (!printerId) {
                this.state.status = 'Impresora no identificada';
                this.state.result = 'error';
                this.state.detail = 'Volvé al listado de impresoras y abrí la prueba desde el equipo.';
                return;
            }
            try {
                Object.assign(this.params, await this.orm.call(
                    'pos.printer', 'action_get_epos_print_test_params', [[printerId]],
                ));
                this.state.status = this.params.last_test_state === 'ok' ? 'Disponible' : 'Lista para probar';
                this.state.result = this.params.last_test_state || 'never';
                this.state.detail = this.params.last_test_at
                    ? `Última prueba registrada: ${this.params.last_test_at}`
                    : 'La prueba envía un ticket de muestra al equipo.';
            } catch (error) {
                this.state.status = 'No se pudo cargar la impresora';
                this.state.result = 'error';
                this.state.detail = error?.message || 'Volvé al listado y abrí la prueba desde el equipo.';
            }
        });
    }

    get receipt() {
        return this.params.receipt_xml || `<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print"><text align="center">TICKET DE PRUEBA&#10;SIN VALOR FISCAL</text><cut type="feed"/></epos-print></s:Body></s:Envelope>`;
    }

    async printTest() {
        if (this.state.busy) return;
        this.state.busy = true;
        this.state.status = 'Conectando e imprimiendo';
        this.state.result = 'connecting';
        this.state.detail = 'El navegador está enviando el ticket de prueba. Revisá la impresora.';
        let finalState = 'error';
        let detail = '';
        try {
            if (this.params.print_protocol === 'escpos_bridge') {
                await this.orm.call('pos.printer', 'action_epos_print_bridge_test', [[this.params.printer_id]]);
            } else {
                const protocol = this.params.use_lna ? 'http:' : window.location.protocol;
                const url = `${protocol}//${this.params.printer_ip}`;
                if (this.params.use_lna) {
                    await initLNA(this.notification);
                }
                const response = await fetch(`${url}/cgi-bin/epos/service.cgi?devid=local_printer`, {
                    method: 'POST',
                    body: this.receipt,
                    signal: AbortSignal.timeout(15000),
                    ...(this.params.use_lna ? { targetAddressSpace: getLNATargetAddressSpace(url) } : {}),
                });
                const xml = new DOMParser().parseFromString(await response.text(), 'application/xml');
                const result = xml.querySelector('response');
                if (!response.ok || !result || result.getAttribute('success') !== 'true' || result.getAttribute('code')) {
                    throw new Error(result?.getAttribute('code') || `HTTP ${response.status}`);
                }
            }
            finalState = 'ok';
            detail = 'La impresora aceptó el trabajo. Confirmá que la muestra salió en papel.';
            this.state.status = 'Disponible';
            this.state.result = 'ok';
            this.state.detail = detail;
            this.notification.add(_t('La impresora aceptó el ticket de prueba.'), { type: 'success' });
        } catch (error) {
            detail = error?.message || 'No se pudo conectar con la impresora desde este navegador.';
            this.state.status = 'No se pudo imprimir';
            this.state.result = 'error';
            this.state.detail = `${detail}. Revisá IP, protocolo y conexión del puente o impresora.`;
            this.notification.add(`${_t('Falló la prueba de impresión.')}: ${detail}`, { type: 'danger' });
        }
        if (this.params.print_protocol !== 'escpos_bridge' || finalState !== 'ok') {
            try {
                await this.orm.call('pos.printer', 'action_record_epos_print_test', [[this.params.printer_id], finalState, detail]);
            } catch {
                this.notification.add(_t('No se pudo guardar el resultado en Odoo.'), { type: 'warning' });
            }
        }
        this.state.busy = false;
    }
}

registry.category('actions').add('epos_print_test', EposPrintTest);
