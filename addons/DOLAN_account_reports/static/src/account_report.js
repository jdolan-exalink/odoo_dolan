/**
 * Informes contables interactivos DOLAN: balance, resultados y sumas y saldos
 * con despliegue de apuntes, comparativos, notas por cuenta y exportación.
 */
import { Component, proxy, useProps, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;

export class DolanAccountReport extends Component {
    static template = "DOLAN_account_reports.Report";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        const context = this.props.action?.context || {};
        const today = DateTime.local();
        this.state = proxy({
            loading: true,
            report: null,
            options: {
                report: context.dolan_report || "balance_sheet",
                date_from: today.startOf("year").toISODate(),
                date_to: today.toISODate(),
                comparison: "none",
                periods: 1,
                posted_only: true,
                hide_zero: true,
            },
            preset: "year",
            unfolded: {},
            drill: {},
            editingNote: null,
            noteDraft: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.report = await this.orm.call("dolan.account.report", "get_report", [this.state.options]);
            for (const accountId of Object.keys(this.state.unfolded)) {
                await this.fetchDrill(Number(accountId));
            }
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------------
    // Filtros
    // ------------------------------------------------------------------
    async setPreset(preset) {
        const today = DateTime.local();
        const ranges = {
            month: [today.startOf("month"), today],
            last_month: [today.minus({ months: 1 }).startOf("month"), today.minus({ months: 1 }).endOf("month")],
            quarter: [today.startOf("quarter"), today],
            year: [today.startOf("year"), today],
            last_year: [today.minus({ years: 1 }).startOf("year"), today.minus({ years: 1 }).endOf("year")],
        };
        this.state.preset = preset;
        if (ranges[preset]) {
            this.state.options.date_from = ranges[preset][0].toISODate();
            this.state.options.date_to = ranges[preset][1].toISODate();
            await this.load();
        }
    }

    async setOption(key, value) {
        this.state.options[key] = value;
        if (key === "date_from" || key === "date_to") {
            this.state.preset = "custom";
        }
        await this.load();
    }

    async setReport(report) {
        this.state.options.report = report;
        this.state.unfolded = {};
        this.state.drill = {};
        await this.load();
    }

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------
    formatAmount(value) {
        const currency = this.state.report?.currency || { digits: 2, symbol: "$", position: "before" };
        const number = (value || 0).toLocaleString("es-AR", {
            minimumFractionDigits: currency.digits,
            maximumFractionDigits: currency.digits,
        });
        return currency.position === "after" ? `${number} ${currency.symbol}` : `${currency.symbol} ${number}`;
    }

    formatVariation(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return `${value > 0 ? "+" : ""}${value.toLocaleString("es-AR", { maximumFractionDigits: 1 })} %`;
    }

    formatDate(value) {
        return value ? DateTime.fromISO(value).toFormat("dd/MM/yyyy") : "";
    }

    lineClass(line) {
        return `o_dolan_report_line o_level_${line.level} o_type_${line.type}`;
    }

    // ------------------------------------------------------------------
    // Despliegue
    // ------------------------------------------------------------------
    async fetchDrill(accountId) {
        this.state.drill[accountId] = await this.orm.call("dolan.account.report", "get_account_lines", [
            this.state.options,
            accountId,
        ]);
    }

    async toggleLine(line) {
        if (!line.foldable) {
            return;
        }
        if (this.state.unfolded[line.account_id]) {
            delete this.state.unfolded[line.account_id];
            delete this.state.drill[line.account_id];
            return;
        }
        this.state.unfolded[line.account_id] = true;
        await this.fetchDrill(line.account_id);
    }

    openMove(moveId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: moveId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAllLines(accountId) {
        const action = await this.orm.call("dolan.account.report", "action_open_move_lines", [
            this.state.options,
            accountId,
        ]);
        this.actionService.doAction(action);
    }

    // ------------------------------------------------------------------
    // Notas
    // ------------------------------------------------------------------
    editNote(line) {
        this.state.editingNote = line.account_id;
        this.state.noteDraft = line.note || "";
    }

    onNoteInput(ev) {
        this.state.noteDraft = ev.target.value;
    }

    async saveNote(line) {
        await this.orm.call("dolan.account.report", "save_note", [
            this.state.options,
            line.account_id,
            this.state.noteDraft,
        ]);
        this.state.editingNote = null;
        await this.load();
        this.notification.add(_t("Nota guardada."), { type: "success" });
    }

    cancelNote() {
        this.state.editingNote = null;
    }

    // ------------------------------------------------------------------
    // Exportar
    // ------------------------------------------------------------------
    async exportXlsx() {
        const action = await this.orm.call("dolan.account.report", "export_xlsx", [this.state.options]);
        this.actionService.doAction(action);
    }

    print() {
        window.print();
    }
}

registry.category("actions").add("dolan_account_report", DolanAccountReport);
