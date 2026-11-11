/**
 * Vistas genéricas DOLAN: Gantt, Mapa, Grilla y Cohorte para cualquier modelo.
 *
 * Cada vista se declara con una etiqueta propia en el arch, por ejemplo:
 *   <dolan_gantt date_start="date_start" date_stop="date_finished" default_group_by="product_id"/>
 *   <dolan_map res_partner="partner_id"/>
 *   <dolan_grid row_field="project_id" date_field="date" measure="unit_amount" range="week" editable="1"/>
 *   <dolan_cohort date_start="create_date" date_stop="date_closed" interval="month"/>
 * Usan el dominio y la agrupación de la barra de búsqueda estándar.
 */
import { Component, signal, t, useProps, proxy, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import {
    deserializeDate,
    deserializeDateTime,
    serializeDate,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { useSetupAction } from "@web/search/action_hook";
import { standardViewProps } from "@web/views/standard_view_props";

const { DateTime } = luxon;
const RECORD_LIMIT = 2000;

function parseArch(arch) {
    const info = { type: arch.tagName };
    for (const { name, value } of arch.attributes) {
        info[name] = value;
    }
    return info;
}

function relId(value) {
    return Array.isArray(value) ? value[0] : value || false;
}

function relName(value, fallback) {
    if (Array.isArray(value)) {
        return value[1];
    }
    if (value === false || value === undefined || value === null || value === "") {
        return fallback;
    }
    return String(value);
}

export class DolanGenericController extends Component {
    static template = "DOLAN_views.GenericView";
    static components = { Layout, SearchBar, CogMenu };
    props = useProps({
        ...standardViewProps,
        archInfo: t.object(),
    });
    rootRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.searchBarToggler = useSearchBarToggler();
        useSetupAction({ rootRef: this.rootRef });
        const info = this.props.archInfo;
        this.state = proxy({
            loading: true,
            scale: info.default_scale || "month",
            anchor: DateTime.local().startOf("day").toISODate(),
            records: [],
            ganttGroups: [],
            ganttColumns: [],
            mapItems: [],
            mapSelected: null,
            gridRows: [],
            gridColumns: [],
            gridTotals: {},
            cohortRows: [],
            cohortColumns: [],
            truncated: false,
        });
        this.dragging = null;
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((nextProps) => this.load(nextProps));
    }

    get info() {
        return this.props.archInfo;
    }

    get title() {
        return this.info.string || "";
    }

    fieldType(name) {
        return this.props.fields[name]?.type;
    }

    fieldLabel(name) {
        return this.props.fields[name]?.string || name;
    }

    // ------------------------------------------------------------------
    // Fechas
    // ------------------------------------------------------------------
    parseDateValue(name, value) {
        if (!value) {
            return null;
        }
        return this.fieldType(name) === "date" ? deserializeDate(value) : deserializeDateTime(value);
    }

    serializeDateValue(name, value) {
        return this.fieldType(name) === "date" ? serializeDate(value) : serializeDateTime(value);
    }

    get range() {
        const anchor = DateTime.fromISO(this.state.anchor);
        const unit = { week: "week", month: "month", quarter: "quarter", year: "year" }[this.state.scale] || "month";
        const start = anchor.startOf(unit);
        return { start, stop: start.plus({ [`${unit}s`]: 1 }), unit };
    }

    get gridRange() {
        const anchor = DateTime.fromISO(this.state.anchor);
        const unit = this.info.range === "month" ? "month" : "week";
        const start = anchor.startOf(unit);
        return { start, stop: start.plus({ [`${unit}s`]: 1 }), unit };
    }

    get rangeLabel() {
        const { start, stop } = this.state.scale && this.info.type === "dolan_grid" ? this.gridRange : this.range;
        const last = stop.minus({ days: 1 });
        return `${start.toFormat("dd/MM/yyyy")} – ${last.toFormat("dd/MM/yyyy")}`;
    }

    async move(direction) {
        const unit = this.info.type === "dolan_grid" ? this.gridRange.unit : this.range.unit;
        const anchor = DateTime.fromISO(this.state.anchor);
        this.state.anchor = direction === 0
            ? DateTime.local().startOf("day").toISODate()
            : anchor.plus({ [`${unit}s`]: direction }).toISODate();
        await this.load(this.props);
    }

    async setScale(scale) {
        this.state.scale = scale;
        await this.load(this.props);
    }

    // ------------------------------------------------------------------
    // Carga
    // ------------------------------------------------------------------
    async load(props) {
        this.state.loading = true;
        try {
            const type = this.info.type;
            if (type === "dolan_gantt") {
                await this.loadGantt(props);
            } else if (type === "dolan_map") {
                await this.loadMap(props);
            } else if (type === "dolan_grid") {
                await this.loadGrid(props);
            } else if (type === "dolan_cohort") {
                await this.loadCohort(props);
            }
        } finally {
            this.state.loading = false;
        }
    }

    async searchRead(props, domain, fieldNames) {
        const fields = [...new Set(fieldNames.filter((name) => name && this.props.fields[name]))];
        const records = await this.orm.searchRead(props.resModel, domain, fields, {
            limit: RECORD_LIMIT,
            context: props.context,
        });
        this.state.truncated = records.length >= RECORD_LIMIT;
        return records;
    }

    groupKeyOf(record, groupField) {
        if (!groupField) {
            return [[false, _t("Todos")]];
        }
        const value = record[groupField];
        if (this.fieldType(groupField) === "many2many" || this.fieldType(groupField) === "one2many") {
            return value && value.length ? value.map((id) => [id, null]) : [[false, _t("Sin asignar")]];
        }
        return [[relId(value) || (value === false ? false : value), relName(value, _t("Sin asignar"))]];
    }

    // ------------------------------------------------------------------
    // Gantt
    // ------------------------------------------------------------------
    async loadGantt(props) {
        const info = this.info;
        const { start, stop } = this.range;
        const startField = info.date_start;
        const stopField = info.date_stop;
        const fallback = info.date_start_fallback;
        const startValue = this.serializeDateValue(startField, start);
        const stopValue = this.serializeDateValue(startField, stop);
        const startTerms = fallback
            ? ["|", [startField, "<", stopValue], "&", [startField, "=", false], [fallback, "<", this.serializeDateValue(fallback, stop)]]
            : [[startField, "<", stopValue]];
        const stopTerms = stopField
            ? ["|", [stopField, ">=", this.serializeDateValue(stopField, start)], [stopField, "=", false]]
            : [[startField, ">=", startValue]];
        const domain = [...props.domain, ...startTerms, ...stopTerms];
        const groupField = props.groupBy[0]?.split(":")[0] || info.default_group_by || null;
        const records = await this.searchRead(props, domain, [
            "display_name", startField, stopField, fallback, groupField, info.progress, info.color,
        ]);

        const totalMs = stop.toMillis() - start.toMillis();
        const groups = new Map();
        const m2mIds = new Set();
        for (const record of records) {
            let recStart = this.parseDateValue(startField, record[startField]);
            if (!recStart && fallback) {
                recStart = this.parseDateValue(fallback, record[fallback]);
            }
            if (!recStart) {
                continue;
            }
            let recStop = stopField ? this.parseDateValue(stopField, record[stopField]) : null;
            if (this.fieldType(stopField) === "date" && recStop) {
                recStop = recStop.plus({ days: 1 });
            }
            if (!recStop || recStop <= recStart) {
                recStop = recStart.plus({ days: 1 });
            }
            const left = Math.max(0, (recStart.toMillis() - start.toMillis()) / totalMs) * 100;
            const right = Math.min(1, (recStop.toMillis() - start.toMillis()) / totalMs) * 100;
            if (right <= 0 || left >= 100) {
                continue;
            }
            const bar = {
                id: record.id,
                name: record.display_name,
                left,
                width: Math.max(right - left, 0.8),
                startLabel: recStart.toFormat("dd/MM/yyyy HH:mm"),
                stopLabel: recStop.toFormat("dd/MM/yyyy HH:mm"),
                progress: info.progress ? Math.round(record[info.progress] || 0) : null,
                color: info.color ? (relId(record[info.color]) || 0) % 12 : record.id % 12,
                movable: Boolean(record[startField]),
            };
            for (const [key, label] of this.groupKeyOf(record, groupField)) {
                if (label === null) {
                    m2mIds.add(key);
                }
                if (!groups.has(key)) {
                    groups.set(key, { key, label, bars: [] });
                }
                groups.get(key).bars.push(bar);
            }
        }
        if (m2mIds.size) {
            const relation = this.props.fields[groupField].relation;
            const names = await this.orm.read(relation, [...m2mIds], ["display_name"]);
            const byId = Object.fromEntries(names.map((rec) => [rec.id, rec.display_name]));
            for (const group of groups.values()) {
                if (group.label === null) {
                    group.label = byId[group.key] || String(group.key);
                }
            }
        }
        this.state.ganttGroups = [...groups.values()].sort((a, b) => String(a.label).localeCompare(String(b.label)));
        this.state.ganttColumns = this.ganttColumns(start, stop);
    }

    ganttColumns(start, stop) {
        const columns = [];
        const step = this.state.scale === "year" ? { months: 1 } : this.state.scale === "quarter" ? { weeks: 1 } : { days: 1 };
        const format = this.state.scale === "year" ? "LLL" : this.state.scale === "quarter" ? "dd/MM" : this.state.scale === "week" ? "ccc dd" : "dd";
        const today = DateTime.local().startOf("day");
        for (let cursor = start; cursor < stop; cursor = cursor.plus(step)) {
            const next = cursor.plus(step);
            columns.push({
                key: cursor.toISODate(),
                label: cursor.toFormat(format),
                today: today >= cursor && today < next,
                weekend: !step.months && !step.weeks && cursor.weekday >= 6,
            });
        }
        return columns;
    }

    onBarPointerDown(ev, bar) {
        if (!bar.movable || this.info.edit === "0") {
            return;
        }
        const track = ev.currentTarget.closest(".o_dolan_gantt_track");
        this.dragging = { bar, startX: ev.clientX, width: track.getBoundingClientRect().width, moved: false };
        const onMove = (moveEv) => {
            if (Math.abs(moveEv.clientX - this.dragging.startX) > 4) {
                this.dragging.moved = true;
                ev.target.closest(".o_dolan_gantt_bar").style.transform =
                    `translateX(${moveEv.clientX - this.dragging.startX}px)`;
            }
        };
        const onUp = async (upEv) => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            const drag = this.dragging;
            this.dragging = null;
            if (!drag.moved) {
                this.openRecord(bar.id);
                return;
            }
            const { start, stop } = this.range;
            const deltaMs = ((upEv.clientX - drag.startX) / drag.width) * (stop.toMillis() - start.toMillis());
            const days = Math.round(deltaMs / 86400000);
            if (days) {
                await this.shiftRecord(bar.id, days);
            } else {
                await this.load(this.props);
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
    }

    async shiftRecord(resId, days) {
        const info = this.info;
        const fieldsToMove = [info.date_start, info.date_stop].filter(Boolean);
        const [record] = await this.orm.read(this.props.resModel, [resId], fieldsToMove);
        const values = {};
        for (const name of fieldsToMove) {
            const value = this.parseDateValue(name, record[name]);
            if (value) {
                values[name] = this.serializeDateValue(name, value.plus({ days }));
            }
        }
        try {
            await this.orm.write(this.props.resModel, [resId], values);
            this.notification.add(_t("Fechas movidas %s día(s).", days), { type: "success" });
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo mover el registro."), { type: "danger" });
        }
        await this.load(this.props);
    }

    openRecord(resId) {
        this.props.selectRecord?.(resId);
    }

    // ------------------------------------------------------------------
    // Mapa
    // ------------------------------------------------------------------
    async loadMap(props) {
        const partnerField = this.info.res_partner;
        const isPartnerModel = props.resModel === "res.partner";
        const records = await this.searchRead(props, props.domain, ["display_name", partnerField]);
        const partnerIds = isPartnerModel
            ? records.map((rec) => rec.id)
            : [...new Set(records.map((rec) => relId(rec[partnerField])).filter(Boolean))];
        const partners = partnerIds.length
            ? await this.orm.read("res.partner", partnerIds, [
                  "display_name", "partner_latitude", "partner_longitude", "contact_address",
              ])
            : [];
        const byId = Object.fromEntries(partners.map((partner) => [partner.id, partner]));
        const items = records.map((record) => {
            const partner = byId[isPartnerModel ? record.id : relId(record[partnerField])] || {};
            const lat = partner.partner_latitude || 0;
            const lon = partner.partner_longitude || 0;
            return {
                id: record.id,
                name: record.display_name,
                partnerName: partner.display_name || "",
                address: (partner.contact_address || "").replace(/\n+/g, ", ").replace(/^[,\s]+|[,\s]+$/g, ""),
                lat,
                lon,
                located: Boolean(lat || lon),
            };
        });
        this.state.mapItems = items;
        const located = items.filter((item) => item.located);
        if (!this.state.mapSelected || !located.find((item) => item.id === this.state.mapSelected.id)) {
            this.state.mapSelected = located[0] || null;
        }
    }

    get mapBounds() {
        const located = this.state.mapItems.filter((item) => item.located);
        if (!located.length) {
            return null;
        }
        const lats = located.map((item) => item.lat);
        const lons = located.map((item) => item.lon);
        const pad = 0.02;
        return {
            minLat: Math.min(...lats) - pad, maxLat: Math.max(...lats) + pad,
            minLon: Math.min(...lons) - pad, maxLon: Math.max(...lons) + pad,
        };
    }

    get mapUrl() {
        const selected = this.state.mapSelected;
        if (!selected) {
            return "";
        }
        const pad = 0.01;
        const bbox = [selected.lon - pad, selected.lat - pad, selected.lon + pad, selected.lat + pad].join(",");
        return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${selected.lat},${selected.lon}`;
    }

    get mapPoints() {
        const bounds = this.mapBounds;
        if (!bounds) {
            return [];
        }
        const spanLat = bounds.maxLat - bounds.minLat || 1;
        const spanLon = bounds.maxLon - bounds.minLon || 1;
        return this.state.mapItems.filter((item) => item.located).map((item) => ({
            ...item,
            x: 5 + ((item.lon - bounds.minLon) / spanLon) * 90,
            y: 12 + (1 - (item.lat - bounds.minLat) / spanLat) * 80,
        }));
    }

    selectMapItem(item) {
        if (item.located) {
            this.state.mapSelected = item;
        }
    }

    routeUrl() {
        const stops = this.state.mapItems.filter((item) => item.located).slice(0, 10);
        if (stops.length < 2) {
            return "";
        }
        return `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${stops.map((s) => `${s.lat},${s.lon}`).join(";")}`;
    }

    // ------------------------------------------------------------------
    // Grilla
    // ------------------------------------------------------------------
    async loadGrid(props) {
        const info = this.info;
        const { start, stop } = this.gridRange;
        const rowField = props.groupBy[0]?.split(":")[0] || info.row_field;
        const domain = [
            ...props.domain,
            [info.date_field, ">=", this.serializeDateValue(info.date_field, start)],
            [info.date_field, "<", this.serializeDateValue(info.date_field, stop)],
        ];
        const records = await this.searchRead(props, domain, [rowField, info.date_field, info.measure]);
        const columns = [];
        for (let cursor = start; cursor < stop; cursor = cursor.plus({ days: 1 })) {
            columns.push({ key: cursor.toISODate(), label: cursor.toFormat("ccc dd"), weekend: cursor.weekday >= 6 });
        }
        const rows = new Map();
        const totals = {};
        for (const record of records) {
            const day = this.parseDateValue(info.date_field, record[info.date_field]);
            if (!day) {
                continue;
            }
            const dayKey = day.toISODate();
            for (const [key, label] of this.groupKeyOf(record, rowField)) {
                if (!rows.has(key)) {
                    rows.set(key, { key, label: label ?? String(key), cells: {}, total: 0 });
                }
                const row = rows.get(key);
                const cell = row.cells[dayKey] || (row.cells[dayKey] = { value: 0, ids: [] });
                cell.value += record[info.measure] || 0;
                cell.ids.push(record.id);
                row.total += record[info.measure] || 0;
                totals[dayKey] = (totals[dayKey] || 0) + (record[info.measure] || 0);
            }
        }
        this.state.gridRowField = rowField;
        this.state.gridColumns = columns;
        this.state.gridRows = [...rows.values()].sort((a, b) => String(a.label).localeCompare(String(b.label)));
        this.state.gridTotals = totals;
    }

    get gridEditable() {
        return this.info.editable === "1" && this.fieldType(this.state.gridRowField) === "many2one";
    }

    gridCell(row, column) {
        return row.cells[column.key] || { value: 0, ids: [] };
    }

    formatAmount(value) {
        return (Math.round((value || 0) * 100) / 100).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    get gridGrandTotal() {
        return Object.values(this.state.gridTotals).reduce((sum, value) => sum + value, 0);
    }

    async onGridCellChange(row, column, ev) {
        const info = this.info;
        const newValue = parseFloat(String(ev.target.value).replace(",", ".")) || 0;
        const cell = this.gridCell(row, column);
        const delta = Math.round((newValue - cell.value) * 100) / 100;
        if (!delta) {
            return;
        }
        try {
            if (cell.ids.length === 1) {
                await this.orm.write(this.props.resModel, cell.ids, { [info.measure]: newValue });
            } else {
                await this.orm.create(this.props.resModel, [{
                    [this.state.gridRowField]: row.key,
                    [info.date_field]: column.key,
                    [info.measure]: delta,
                }], { context: this.props.context });
            }
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo guardar la celda."), { type: "danger" });
        }
        await this.load(this.props);
    }

    // ------------------------------------------------------------------
    // Cohorte
    // ------------------------------------------------------------------
    async loadCohort(props) {
        const info = this.info;
        const interval = ["day", "week", "month", "year"].includes(info.interval) ? info.interval : "month";
        const periods = parseInt(info.periods || "12", 10);
        const now = DateTime.local().startOf(interval);
        const first = now.minus({ [`${interval}s`]: periods - 1 });
        const domain = [...props.domain, [info.date_start, ">=", this.serializeDateValue(info.date_start, first)]];
        const measure = info.measure && info.measure !== "__count" ? info.measure : null;
        const records = await this.searchRead(props, domain, [info.date_start, info.date_stop, measure]);
        const rows = [];
        for (let index = 0; index < periods; index++) {
            const periodStart = first.plus({ [`${interval}s`]: index });
            rows.push({ key: periodStart.toISODate(), label: this.periodLabel(periodStart, interval), start: periodStart, records: [] });
        }
        for (const record of records) {
            const start = this.parseDateValue(info.date_start, record[info.date_start]);
            if (!start) {
                continue;
            }
            const index = Math.floor(start.startOf(interval).diff(first, `${interval}s`)[`${interval}s`] + 0.0001);
            if (rows[index]) {
                rows[index].records.push(record);
            }
        }
        const weight = (record) => (measure ? record[measure] || 0 : 1);
        this.state.cohortColumns = [...Array(periods).keys()];
        this.state.cohortRows = rows.map((row, rowIndex) => {
            const total = row.records.reduce((sum, record) => sum + weight(record), 0);
            const cells = this.state.cohortColumns.map((offset) => {
                if (rowIndex + offset >= periods) {
                    return null;
                }
                const limit = row.start.plus({ [`${interval}s`]: offset + 1 });
                const active = row.records.reduce((sum, record) => {
                    const stop = info.date_stop ? this.parseDateValue(info.date_stop, record[info.date_stop]) : null;
                    return !stop || stop >= limit ? sum + weight(record) : sum;
                }, 0);
                const pct = total ? Math.round((active / total) * 1000) / 10 : 0;
                return { pct, level: Math.min(9, Math.floor(pct / 11)) };
            });
            return { key: row.key, label: row.label, total, cells };
        });
    }

    periodLabel(date, interval) {
        if (interval === "year") {
            return date.toFormat("yyyy");
        }
        if (interval === "month") {
            return date.toFormat("LLL yyyy");
        }
        if (interval === "week") {
            return _t("Sem. %s", date.toFormat("WW yyyy"));
        }
        return date.toFormat("dd/MM/yyyy");
    }

    get cohortMeasureLabel() {
        const measure = this.info.measure;
        return measure && measure !== "__count" ? this.fieldLabel(measure) : _t("Cantidad");
    }
}

function makeView(type) {
    return {
        type,
        Controller: DolanGenericController,
        searchMenuTypes: ["filter", "groupBy", "favorite"],
        props: (genericProps) => ({
            ...genericProps,
            archInfo: parseArch(genericProps.arch),
        }),
    };
}

for (const type of ["dolan_gantt", "dolan_map", "dolan_grid", "dolan_cohort"]) {
    registry.category("views").add(type, makeView(type));
}
