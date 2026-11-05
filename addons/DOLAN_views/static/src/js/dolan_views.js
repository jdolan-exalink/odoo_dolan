/** @odoo-module **/

import { Component, proxy, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DolanMultiViewPlanner extends Component {
    static template = "DOLAN_views.MultiViewPlanner";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = proxy({
            activeMode: "gantt", // 'gantt' | 'cohort' | 'grid' | 'map'
            categoryFilter: "all",
            loading: true,
            ganttRows: [],
            cohortRows: [],
            gridDays: [],
            gridRows: [],
            mapMarkers: [],
            selectedMarker: null,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "dolan.view.planner.item",
                "get_multiview_dashboard_data",
                [this.state.categoryFilter, "week"]
            );
            this.state.ganttRows = data.gantt_rows || [];
            this.state.cohortRows = data.cohort_rows || [];
            this.state.gridDays = data.grid_days || [];
            this.state.gridRows = data.grid_rows || [];
            this.state.mapMarkers = data.map_markers || [];
            if (this.state.mapMarkers.length && !this.state.selectedMarker) {
                this.state.selectedMarker = this.state.mapMarkers[0];
            }
        } finally {
            this.state.loading = false;
        }
    }

    async setMode(mode) {
        this.state.activeMode = mode;
    }

    async onCategoryChange(ev) {
        this.state.categoryFilter = ev.target.value;
        await this.loadDashboardData();
    }

    async onProgressStep(row, delta) {
        const nextProgress = Math.max(0, Math.min(100, (row.progress || 0) + delta));
        await this.orm.call("dolan.view.planner.item", "update_item_progress", [
            row.id,
            nextProgress,
        ]);
        await this.loadDashboardData();
    }

    async onGridCellChange(row, dayIso, ev) {
        const hours = parseFloat(ev.target.value || "0");
        await this.orm.call("dolan.view.planner.item", "update_grid_cell", [
            row.sample_item_id,
            dayIso,
            hours,
        ]);
        this.notification.add("Horas actualizadas en la grilla semanal.", {
            type: "success",
        });
        await this.loadDashboardData();
    }

    selectMarker(marker) {
        this.state.selectedMarker = marker;
    }

    openRecordsList() {
        this.action.doAction("DOLAN_views.action_dolan_view_planner_items");
    }
}

registry.category("actions").add("dolan_views.multiview_planner", DolanMultiViewPlanner);
