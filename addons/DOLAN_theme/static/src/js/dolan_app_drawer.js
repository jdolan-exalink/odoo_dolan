/** @odoo-module **/

import { Component, proxy, signal, onMounted, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { DolanIcon } from "./dolan_icon";
import { NavBar } from "@web/webclient/navbar/navbar";

/**
 * Patch de NavBar en OWL 3:
 * Conecta el botón toggle Enterprise (.o_menu_toggle) y el botón All Apps del sidebar
 * móvil directamente con el bus de Odoo, eliminando la dependencia de manipulaciones DOM frágiles.
 */
patch(NavBar.prototype, {
    toggleDolanAppDrawer() {
        this.env.bus.trigger("DOLAN:TOGGLE_APP_DRAWER");
    },
    openDolanAppDrawer() {
        // La casita siempre ABRE el Menú de Inicio; nunca lo cierra por toggle.
        this.env.bus.trigger("DOLAN:OPEN_APP_DRAWER");
    },
    onAllAppsBtnClick() {
        if (this.state && this.state.isAppMenuSidebarOpened !== undefined) {
            this.state.isAppMenuSidebarOpened = false;
        }
        this.toggleDolanAppDrawer();
    },
});

/**
 * SVG exacto de 14x14px (3 filas x 3 rectángulos) de Odoo 20 Enterprise (.o_menu_toggle)
 * que se transforma en una flecha de retorno al pasar el mouse.
 */
export const ENTERPRISE_TOGGLE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14" class="o_menu_toggle_icon">
    <g fill="currentColor" id="o_menu_toggle_row_0">
        <rect width="3" height="3" x="0" y="0" rx="0.5"/>
        <rect width="3" height="3" x="5.5" y="0" rx="0.5"/>
        <rect width="3" height="3" x="11" y="0" rx="0.5"/>
    </g>
    <g fill="currentColor" id="o_menu_toggle_row_1">
        <rect width="3" height="3" x="0" y="5.5" rx="0.5"/>
        <rect width="3" height="3" x="5.5" y="5.5" rx="0.5"/>
        <rect width="3" height="3" x="11" y="5.5" rx="0.5"/>
    </g>
    <g fill="currentColor" id="o_menu_toggle_row_2">
        <rect width="3" height="3" x="0" y="11" rx="0.5"/>
        <rect width="3" height="3" x="5.5" y="11" rx="0.5"/>
        <rect width="3" height="3" x="11" y="11" rx="0.5"/>
    </g>
</svg>`;

/**
 * Decide whether the app drawer's global key handler may process this target.
 * Text editors outside the drawer's own search must keep their keystrokes.
 */
/**
 * Mantiene la cookie nativa `color_scheme` de Odoo en sync con el modo oscuro
 * DOLAN. Los renderers basados en canvas (dashboards o-spreadsheet, vistas
 * graph, campos ace) no pueden ver la clase body.o_dolan_dark_mode: leen esta
 * cookie al cargarse para pintar su variante oscura. Cookie ausente = claro.
 */
export function syncColorSchemeCookie(isDark) {
    if (isDark) {
        document.cookie = "color_scheme=dark;path=/;max-age=31536000;SameSite=Lax";
    } else {
        document.cookie = "color_scheme=;path=/;max-age=0";
    }
}

export function shouldHandleAppDrawerKeydown(target, searchInput) {
    const isElement = target instanceof Element;
    const isAppSearch = target === searchInput;
    const isOtherEditor = isElement && (
        target.matches('input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="textbox"]') ||
        Boolean(target.closest('.o_dolan_ai_drawer'))
    );
    return !(isOtherEditor && !isAppSearch);
}

export class DolanAppDrawerSystray extends Component {
    static template = "DOLAN_theme.AppDrawerSystray";
    static components = { DolanIcon };

    searchInputRef = signal.ref();

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");

        // Escuchar eventos globales del bus disparados desde NavBar o cualquier módulo
        useBus(this.env.bus, "DOLAN:TOGGLE_APP_DRAWER", () => this.toggleDrawer());
        useBus(this.env.bus, "DOLAN:OPEN_APP_DRAWER", () => this.openDrawer());
        useBus(this.env.bus, "DOLAN:CLOSE_APP_DRAWER", () => this.closeDrawer());
        useBus(this.env.bus, "DOLAN:OPEN_APP_SEARCH", () => {
            this.setTab("apps");
            this.openDrawer();
            setTimeout(() => this.searchInputRef()?.focus(), 60);
        });
        useBus(this.env.bus, "DOLAN:OPEN_QUICK_ACTIONS", () => {
            this.setTab("workspace");
            this.openDrawer();
        });

        const savedDark = window.localStorage.getItem("dolan_dark_mode") === "1";
        if (savedDark) {
            document.body.classList.add("o_dolan_dark_mode");
        }
        syncColorSchemeCookie(savedDark);

        const savedCompact = window.localStorage.getItem("dolan_density") === "compact";
        document.body.classList.toggle("o_dolan_compact", savedCompact);

        const initialOpen =
            window.location.pathname === "/odoo" ||
            window.location.pathname === "/odoo/" ||
            window.location.pathname === "/web";
        if (initialOpen) {
            document.body.classList.add("o_home_menu_background");
        }

        this.state = proxy({
            isOpen: initialOpen,
            query: "",
            selectedIndex: 0,
            darkMode: savedDark,
            hiddenAppXmlids: [],
            activeTab: "apps",
            kpis: [],
            kpisLoading: false,
            kpisError: false,
            roleFilter: window.localStorage.getItem("dolan_workspace_role") || "all",
            compact: savedCompact,
            favorites: this._loadJson("dolan_favorite_apps", []),
            recents: this._loadJson("dolan_recent_apps", []),
            kpiStates: this._loadJson("dolan_kpi_states", {}),
        });

        this._lastToggle = 0;

        this._onGlobalKeydown = (ev) => {
            // Keep Odoo's global app search and navigation out of text editors,
            // especially DOLAN AI's composer.
            if (!shouldHandleAppDrawerKeydown(ev.target, this.searchInputRef())) {
                return;
            }
            if (ev.altKey && (ev.key === "q" || ev.key === "Q" || ev.key === "h" || ev.key === "H")) {
                ev.preventDefault();
                this.toggleDrawer();
                return;
            }
            if (!this.state.isOpen) {
                return;
            }
            if (ev.key === "Escape") {
                ev.preventDefault();
                if (this.state.query) {
                    this.state.query = "";
                    this.state.selectedIndex = 0;
                } else {
                    this.closeDrawer();
                }
                return;
            }
            const inputEl = this.searchInputRef();
            if (
                ev.key.length === 1 &&
                !ev.ctrlKey &&
                !ev.metaKey &&
                !ev.altKey &&
                document.activeElement !== inputEl
            ) {
                if (inputEl) {
                    inputEl.focus();
                }
            }
            this.onKeydown(ev);
        };

        // Delegated capture listener as a fail-safe:
        // Any click on .o_menu_toggle, .o_dolan_enterprise_toggle, or .o_navbar_apps_menu button
        // triggers toggleDrawer() even if hydration or route changes occur.
        this._onDocumentClick = (ev) => {
            const toggleBtn = ev.target.closest(".o_dolan_enterprise_toggle, .o_menu_toggle, .o_navbar_apps_menu button");
            if (toggleBtn && !toggleBtn.closest(".o_dolan_home_menu_wrapper")) {
                ev.preventDefault();
                ev.stopPropagation();
                this.toggleDrawer();
            }
        };

        onMounted(() => {
            window.addEventListener("keydown", this._onGlobalKeydown);
            document.addEventListener("click", this._onDocumentClick, true);
            this.loadScreenPreferences();
        });

        onWillDestroy(() => {
            window.removeEventListener("keydown", this._onGlobalKeydown);
            document.removeEventListener("click", this._onDocumentClick, true);
            document.body.classList.remove("o_home_menu_background");
        });
    }

    _syncBodyClass() {
        document.body.classList.toggle("o_home_menu_background", this.state.isOpen);
    }

    get apps() {
        try {
            return this.menuService.getApps() || [];
        } catch {
            return [];
        }
    }

    get filteredApps() {
        const visibleApps = this.visibleApps;
        const q = (this.state.query || "").trim().toLowerCase();
        if (!q) {
            const favs = this.state.favorites;
            return [...visibleApps].sort(
                (a, b) => Number(favs.includes(b.id)) - Number(favs.includes(a.id))
            );
        }
        return visibleApps.filter((app) => (app.name || "").toLowerCase().includes(q));
    }

    get recentApps() {
        const byId = new Map(this.visibleApps.map((a) => [a.id, a]));
        return this.state.recents.map((id) => byId.get(id)).filter(Boolean);
    }

    get visibleApps() {
        return this.apps.filter((app) => !this.state.hiddenAppXmlids.includes(app.xmlid));
    }

    isFavorite(app) {
        return this.state.favorites.includes(app.id);
    }

    toggleFavorite(app) {
        const favs = this.state.favorites;
        const next = favs.includes(app.id) ? favs.filter((id) => id !== app.id) : [...favs, app.id];
        this.state.favorites = next;
        this._saveJson("dolan_favorite_apps", next);
    }

    _loadJson(key, fallback) {
        try {
            const value = JSON.parse(window.localStorage.getItem(key));
            return value ?? fallback;
        } catch {
            return fallback;
        }
    }

    _saveJson(key, value) {
        window.localStorage.setItem(key, JSON.stringify(value));
    }

    // --- Centro de atención: posponer / marcar como leído (PRD 04 §13) ---
    _isHiddenKpi(kpi) {
        const entry = this.state.kpiStates[kpi.key];
        if (!entry) {
            return false;
        }
        if (entry.dismissedCount !== undefined) {
            // Leído: vuelve a aparecer solo si el conteo crece.
            if (kpi.count > entry.dismissedCount) {
                return false;
            }
            return true;
        }
        return entry.snoozeUntil && entry.snoozeUntil > Date.now();
    }

    snoozeKpi(kpi) {
        this._setKpiState(kpi.key, { snoozeUntil: Date.now() + 24 * 3600 * 1000 });
    }

    dismissKpi(kpi) {
        this._setKpiState(kpi.key, { dismissedCount: kpi.count });
    }

    restoreKpis() {
        this.state.kpiStates = {};
        this._saveJson("dolan_kpi_states", {});
    }

    _setKpiState(key, entry) {
        const next = { ...this.state.kpiStates, [key]: entry };
        this.state.kpiStates = next;
        this._saveJson("dolan_kpi_states", next);
    }

    get hiddenKpiCount() {
        return (this.state.kpis || []).filter((k) => this._isHiddenKpi(k)).length;
    }

    getAppIconUrl(app) {
        if (typeof app.webIcon === "string" && app.webIcon.includes(",")) {
            const [mod, iconPath] = app.webIcon.split(",");
            return `/${mod.trim()}/${iconPath.trim().replace(/^\/+/, "")}`;
        }
        if (app.webIconData) {
            return app.webIconData;
        }
        return null;
    }

    static isHomePath(pathname = window.location.pathname) {
        return pathname === "/odoo" || pathname === "/odoo/" || pathname === "/web";
    }

    openDrawer() {
        if (this.state.isOpen) {
            return;
        }
        // La URL debe reflejar que estamos en el launcher: así F5 se queda aquí
        // en lugar de saltar a la última app.
        if (!DolanAppDrawerSystray.isHomePath()) {
            window.sessionStorage.setItem(
                "dolan_return_url",
                window.location.pathname + window.location.search + window.location.hash
            );
            window.history.pushState({ dolanHome: true }, "", "/odoo");
            this._pushedHome = true;
        }
        this.state.isOpen = true;
        this.loadScreenPreferences();
        this.state.query = "";
        this.state.selectedIndex = 0;
        this._syncBodyClass();
        setTimeout(() => {
            const inputEl = this.searchInputRef();
            if (inputEl) {
                inputEl.focus();
            }
        }, 50);
    }

    /**
     * @param {Object} [options]
     * @param {boolean} [options.restore=true] volver a la pantalla previa (false al elegir una app)
     */
    closeDrawer({ restore = true } = {}) {
        const wasOpen = this.state.isOpen;
        this.state.isOpen = false;
        this.state.query = "";
        this._syncBodyClass();
        if (!wasOpen || !restore || !DolanAppDrawerSystray.isHomePath()) {
            this._pushedHome = false;
            return;
        }
        if (this._pushedHome) {
            // Odoo reacciona a popstate y recarga la vista anterior sin recargar la página.
            this._pushedHome = false;
            window.history.back();
            return;
        }
        // Tras un F5 en el launcher no hay historial propio: usar la última pantalla guardada.
        const back = window.sessionStorage.getItem("dolan_return_url");
        if (back && !DolanAppDrawerSystray.isHomePath(back.split(/[?#]/)[0])) {
            window.location.assign(back);
        }
    }

    toggleDrawer() {
        const now = Date.now();
        if (this._lastToggle && now - this._lastToggle < 200) {
            return;
        }
        this._lastToggle = now;
        if (this.state.isOpen) {
            this.closeDrawer();
        } else {
            this.openDrawer();
        }
    }

    toggleDarkMode() {
        this.state.darkMode = !this.state.darkMode;
        document.body.classList.toggle("o_dolan_dark_mode", this.state.darkMode);
        window.localStorage.setItem("dolan_dark_mode", this.state.darkMode ? "1" : "0");
        syncColorSchemeCookie(this.state.darkMode);
        this.saveScreenPreferences({ theme_mode: this.state.darkMode ? "dark" : "light" });
    }

    async loadScreenPreferences() {
        try {
            const response = await rpc("/dolan_theme/screen_preferences", {
                values: {
                    theme_mode: window.localStorage.getItem("dolan_dark_mode") === "1" ? "dark" : "light",
                    compact_mode: window.localStorage.getItem("dolan_density") === "compact",
                },
            });
            this.state.darkMode = response.theme_mode === "dark";
            this.state.compact = Boolean(response.compact_mode);
            this.state.hiddenAppXmlids = response.hidden_app_xmlids || [];
            document.body.classList.toggle("o_dolan_dark_mode", this.state.darkMode);
            document.body.classList.toggle("o_dolan_compact", this.state.compact);
            window.localStorage.setItem("dolan_dark_mode", this.state.darkMode ? "1" : "0");
            window.localStorage.setItem("dolan_density", this.state.compact ? "compact" : "normal");
            syncColorSchemeCookie(this.state.darkMode);
        } catch {
            // Conservar preferencias locales si el servidor no está disponible.
        }
    }

    async saveScreenPreferences(values) {
        try {
            await rpc("/dolan_theme/screen_preferences", { values });
        } catch {
            // El tema sigue funcionando localmente aunque no se pueda sincronizar.
        }
    }

    get visibleKpis() {
        const role = this.state.roleFilter;
        const kpis = this.state.kpis || [];
        const byRole = role === "all" ? kpis : kpis.filter((k) => k.role === role || k.role === "general");
        return byRole.filter((k) => !this._isHiddenKpi(k));
    }

    get kpiRoles() {
        const labels = {
            administracion: "Administración", ventas: "Ventas", compras: "Compras",
            deposito: "Depósito", produccion: "Producción", mantenimiento: "Mantenimiento",
        };
        const present = new Set((this.state.kpis || []).map((k) => k.role));
        return Object.keys(labels).filter((r) => present.has(r)).map((r) => ({ key: r, label: labels[r] }));
    }

    setRoleFilter(role) {
        this.state.roleFilter = role;
        window.localStorage.setItem("dolan_workspace_role", role);
    }

    async loadKpis() {
        this.state.kpisLoading = true;
        try {
            const res = await rpc("/dolan_theme/workspace_kpis", {});
            this.state.kpis = res.kpis || [];
            this.state.kpisError = false;
        } catch {
            this.state.kpisError = true;
        } finally {
            this.state.kpisLoading = false;
        }
    }

    openKpi(kpi) {
        this.closeDrawer({ restore: false });
        if (kpi.model === "mail.activity") {
            return;
        }
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: kpi.label,
            res_model: kpi.model,
            views: [[false, "list"], [false, "form"]],
            domain: kpi.domain,
        });
    }

    toggleDensity() {
        this.state.compact = !this.state.compact;
        document.body.classList.toggle("o_dolan_compact", this.state.compact);
        window.localStorage.setItem("dolan_density", this.state.compact ? "compact" : "normal");
        this.saveScreenPreferences({ compact_mode: this.state.compact });
    }

    setTab(tab) {
        this.state.activeTab = tab;
        if (tab === "mine") {
            this.loadKpis();
        }
        if (tab === "apps") {
            setTimeout(() => {
                const el = this.searchInputRef();
                if (el) el.focus();
            }, 50);
        }
    }

    executeQuickAction(actionKey) {
        this.closeDrawer({ restore: false });
        switch (actionKey) {
            case "new_invoice":
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "account.move",
                    views: [[false, "form"]],
                    context: { default_move_type: "out_invoice" },
                });
                break;
            case "new_sale":
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "sale.order",
                    views: [[false, "form"]],
                });
                break;
            case "new_partner":
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "res.partner",
                    views: [[false, "form"]],
                });
                break;
            case "new_payment":
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "account.payment",
                    views: [[false, "form"]],
                });
                break;
            case "whatsapp":
                this.actionService.doAction("DOLAN_whatsapp.action_dolan_whatsapp_messages");
                break;
            case "libro_iva":
                this.actionService.doAction("DOLAN_l10n_ar_afip.action_l10n_ar_libro_iva_digital_wizard");
                break;
            case "open_search":
                window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
                break;
            case "toggle_ai":
                this.env.bus.trigger("DOLAN:TOGGLE_AI_CHAT");
                break;
        }
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value;
        this.state.selectedIndex = 0;
    }

    onKeydown(ev) {
        const list = this.filteredApps;
        if (!list.length) {
            return;
        }
        const cols = window.innerWidth >= 768 ? 6 : 4;
        if (ev.key === "ArrowRight") {
            ev.preventDefault();
            this.state.selectedIndex = (this.state.selectedIndex + 1) % list.length;
        } else if (ev.key === "ArrowLeft") {
            ev.preventDefault();
            this.state.selectedIndex = (this.state.selectedIndex - 1 + list.length) % list.length;
        } else if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.selectedIndex = Math.min(list.length - 1, this.state.selectedIndex + cols);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.selectedIndex = Math.max(0, this.state.selectedIndex - cols);
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const chosen = list[this.state.selectedIndex] || list[0];
            if (chosen) {
                this.selectApp(chosen);
            }
        }
    }

    selectApp(app) {
        const recents = [app.id, ...this.state.recents.filter((id) => id !== app.id)].slice(0, 6);
        this.state.recents = recents;
        this._saveJson("dolan_recent_apps", recents);
        this.closeDrawer({ restore: false });
        this.menuService.selectMenu(app);
    }
}

registry.category("systray").add(
    "DOLAN_theme.AppDrawerSystray",
    { Component: DolanAppDrawerSystray },
    { sequence: 100 }
);
