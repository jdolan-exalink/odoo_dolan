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

export function sortDesktopApps(apps, mode, usageCounts = {}, items = [], locale = undefined) {
    // Odoo locales use underscores (for example `es_AR`), while Intl expects
    // BCP 47 tags (`es-AR`). Guard malformed/custom locale codes so one bad
    // language setting cannot crash the whole navbar and leave the web client blank.
    const normalizedLocale = typeof locale === "string" ? locale.replaceAll("_", "-") : locale;
    let collator;
    try {
        collator = new Intl.Collator(normalizedLocale, { sensitivity: "base", numeric: true });
    } catch {
        collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
    }
    const key = (app) => app.xmlid || `menu:${app.id}`;
    const alpha = (a, b) => collator.compare(a.name || "Aplicación", b.name || "Aplicación") || a.id - b.id;
    const result = [...apps];
    if (mode === "alphabetical") return result.sort(alpha);
    if (mode === "most_used") {
        result.sort((a, b) =>
            Number(usageCounts[key(a)] || 0) - Number(usageCounts[key(b)] || 0) || alpha(a, b)
        );
        const mostUsed = result.slice(-3).sort((a, b) =>
            Number(usageCounts[key(b)] || 0) - Number(usageCounts[key(a)] || 0) || alpha(a, b)
        );
        return [...result.slice(0, -3), ...mostUsed];
    }
    const positions = new Map(items.map((item, index) => [item.menu_key, item.sequence ?? index]));
    return result.sort((a, b) => {
        const pa = positions.has(key(a)) ? Number(positions.get(key(a))) : Number.MAX_SAFE_INTEGER;
        const pb = positions.has(key(b)) ? Number(positions.get(key(b))) : Number.MAX_SAFE_INTEGER;
        return pa - pb || alpha(a, b);
    });
}

export class DolanAppDrawerSystray extends Component {
    static template = "DOLAN_theme.AppDrawerSystray";
    static components = { DolanIcon };

    searchInputRef = signal.ref();

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.notification = useService("notification");

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
            this.setTab("mine");
            this.openDrawer();
            setTimeout(() => document.querySelector(".o_dolan_quick_actions_widget")?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
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

        this._desktopInitialApplied = false;
        this.state = proxy({
            isOpen: initialOpen,
            query: "",
            selectedIndex: -1,
            darkMode: savedDark,
            hiddenAppXmlids: [],
            activeTab: "apps",
            sortMode: "most_used",
            landingView: "apps",
            showRecents: true,
            layoutVersion: 0,
            desktopItems: [],
            desktopFolders: [],
            desktopDraggingKey: null,
            desktopDraggingFolderId: null,
            desktopDraggingFolderKey: null,
            desktopDropTargetKey: null,
            desktopDropTargetFolderId: null,
            desktopPointerDropType: null,
            openFolderId: null,
            folderNameEditId: null,
            folderNameDraft: "",
            folderDraft: null,
            desktopLayoutSaving: false,
            usageCounts: {},
            recentKeys: [],
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
        this._desktopPointerDrag = null;
        this._suppressDesktopClick = null;

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
                if (this.state.folderDraft) {
                    this.state.folderDraft = null;
                } else if (this.state.openFolderId) {
                    this.closeDesktopFolder();
                } else if (this.state.query) {
                    this.state.query = "";
                    this.state.selectedIndex = -1;
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
            const suppressed = this._suppressDesktopClick;
            if (suppressed && suppressed.until >= Date.now()) {
                const appCell = ev.target.closest(".o_dolan_app_cell[data-menu-key]");
                const folderCell = ev.target.closest(".o_dolan_folder_cell[data-folder-id]");
                if (appCell || folderCell) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    ev.stopImmediatePropagation();
                    this._suppressDesktopClick = null;
                    return;
                }
            }
            const toggleBtn = ev.target.closest(".o_dolan_enterprise_toggle, .o_menu_toggle, .o_navbar_apps_menu button");
            if (toggleBtn && !toggleBtn.closest(".o_dolan_home_menu_wrapper")) {
                ev.preventDefault();
                ev.stopPropagation();
                this.toggleDrawer();
            }
        };

        this._onDesktopPointerDown = (ev) => {
            if (ev.button !== 0 || ev.pointerType !== "mouse" || ev.isPrimary === false || this.state.query) return;
            const appCell = ev.target.closest(".o_dolan_app_cell[data-menu-key]");
            const folderApp = ev.target.closest(".o_dolan_folder_app[data-menu-key]");
            const folderCell = ev.target.closest(".o_dolan_folder_cell[data-folder-id]");
            const source = folderApp || appCell;
            if (!source && !folderCell) return;
            if (ev.target.closest(".o_dolan_fav_btn, .o_dolan_app_reorder_controls, .o_dolan_folder_order")) return;
            if (ev.target.closest("button") && !folderApp && !folderCell) return;
            if (folderCell) {
                const folder = this.state.desktopFolders.find((item) => item.id === Number(folderCell.dataset.folderId));
                if (!folder) return;
                this._desktopPointerDrag = {
                    pointerId: ev.pointerId, kind: "folder", folderId: folder.id,
                    x: ev.clientX, y: ev.clientY, moved: false, rootTileOrder: this.rootTileOrder,
                };
                return;
            }
            const key = source.dataset.menuKey;
            const app = this.orderedApps.find((item) => this.appDesktopKey(item) === key);
            if (!app) return;
            this._desktopPointerDrag = {
                pointerId: ev.pointerId,
                kind: "app",
                key,
                app,
                sourceFolderId: folderApp ? this.state.openFolderId : false,
                rootTileOrder: this.rootTileOrder,
                x: ev.clientX,
                y: ev.clientY,
                moved: false,
            };
        };
        this._onDesktopPointerMove = (ev) => {
            const drag = this._desktopPointerDrag;
            if (!drag || ev.pointerId !== drag.pointerId) return;
            if (!drag.moved && Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y) < 7) return;
            drag.moved = true;
            ev.preventDefault();
            this.state.desktopDraggingKey = drag.key;
            this.state.desktopDraggingFolderId = drag.sourceFolderId;
            this.state.desktopDraggingFolderKey = drag.kind === "folder" ? drag.folderId : null;
            const under = document.elementFromPoint(ev.clientX, ev.clientY);
            const folderCell = under?.closest(".o_dolan_folder_cell[data-folder-id]");
            const rootAppCell = under?.closest(".o_dolan_root_app_grid .o_dolan_app_cell[data-menu-key]");
            const folderContents = under?.closest(".o_dolan_folder_contents");
            const rootDrop = under?.closest(".o_dolan_folder_root_drop");
            const folderDialog = under?.closest(".o_dolan_folder_dialog");
            const rootGrid = under?.closest(".o_dolan_root_app_grid");
            const dropKey = rootAppCell?.dataset.menuKey || null;
            const dropFolderId = folderCell ? Number(folderCell.dataset.folderId) :
                (folderContents || folderDialog) ? this.state.openFolderId : null;
            if (this.state.desktopDropTargetKey !== dropKey) this.state.desktopDropTargetKey = dropKey;
            if (this.state.desktopDropTargetFolderId !== dropFolderId) this.state.desktopDropTargetFolderId = dropFolderId;
            this.state.desktopPointerDropType = rootDrop ? "root" : folderCell ? "folder" :
                folderContents ? "folder_contents" : folderDialog ? "folder_dialog" : rootAppCell ? "app" : null;
            if (drag.kind === "folder") {
                this.state.desktopDropTargetFolderId = folderCell ? Number(folderCell.dataset.folderId) : null;
                this.state.desktopDropTargetKey = null;
            }
        };
        this._onDesktopPointerUp = async (ev) => {
            const drag = this._desktopPointerDrag;
            if (!drag || ev.pointerId !== drag.pointerId) return;
            this._desktopPointerDrag = null;
            if (!drag.moved) return;
            ev.preventDefault();
            ev.stopPropagation();
            this._suppressDesktopClick = {
                key: drag.key,
                folderId: drag.kind === "folder" ? drag.folderId : null,
                until: Date.now() + 700,
            };
            const under = document.elementFromPoint(ev.clientX, ev.clientY);
            const folderCell = under?.closest(".o_dolan_folder_cell[data-folder-id]");
            const rootAppCell = under?.closest(".o_dolan_root_app_grid .o_dolan_app_cell[data-menu-key]");
            const folderContents = under?.closest(".o_dolan_folder_contents");
            const rootDrop = under?.closest(".o_dolan_folder_root_drop");
            const folderDialog = under?.closest(".o_dolan_folder_dialog");
            const rootGrid = under?.closest(".o_dolan_root_app_grid");
            const target = rootDrop || folderCell || folderContents || folderDialog || rootAppCell;
            const targetTile = under?.closest("[data-desktop-tile-key]");
            const targetTileKey = targetTile?.dataset.desktopTileKey || null;
            const targetApp = rootAppCell
                ? this.orderedApps.find((item) => this.appDesktopKey(item) === rootAppCell.dataset.menuKey)
                : folderContents
                    ? this.orderedApps.find((item) => this.appDesktopKey(item) === under?.closest("[data-menu-key]")?.dataset.menuKey)
                    : null;
            if (drag.kind === "folder") {
                if (targetTileKey && targetTileKey !== `folder:${drag.folderId}`) {
                    await this.reorderDesktopTile(drag, targetTileKey, ev.clientX, ev.clientY, targetTile);
                } else if (rootGrid) {
                    await this.reorderDesktopTile(drag, null, ev.clientX, ev.clientY, rootGrid);
                } else this.onDesktopAppDragEnd();
                return;
            }
            if (this.state.sortMode !== "custom") {
                this.state.sortMode = "custom";
                await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
            }
            this.state.desktopDraggingKey = drag.key;
            this.state.desktopDraggingFolderId = drag.sourceFolderId;
            const event = {
                target: under,
                currentTarget: target,
                clientX: ev.clientX,
                clientY: ev.clientY,
                preventDefault() {},
                dataTransfer: { getData: () => drag.key },
            };
            if (rootDrop) {
                await this.reorderDesktopTile(drag, null, ev.clientX, ev.clientY, null, { append: true });
            } else if (folderContents || folderDialog) {
                if (this.openFolder) await this.onFolderContentsDrop(this.openFolder, event);
            } else if (folderCell) {
                const folder = this.state.desktopFolders.find((item) => item.id === Number(folderCell.dataset.folderId));
                if (folder) await this.onDesktopAppDrop(null, event, folder.id, drag.rootTileOrder);
            } else if (rootAppCell) {
                if (drag.sourceFolderId) {
                    await this.reorderDesktopTile(drag, targetTileKey, ev.clientX, ev.clientY, rootAppCell);
                } else {
                    const rect = rootAppCell.getBoundingClientRect();
                    const x = rect.width ? (ev.clientX - rect.left) / rect.width : 0.5;
                    const y = rect.height ? (ev.clientY - rect.top) / rect.height : 0.5;
                    if (x > 0.25 && x < 0.75 && y > 0.25 && y < 0.75) {
                        await this.onDesktopAppDrop(targetApp || drag.app, event, false, drag.rootTileOrder);
                    } else {
                        await this.reorderDesktopTile(drag, targetTileKey, ev.clientX, ev.clientY, rootAppCell);
                    }
                }
            } else if (rootGrid) {
                await this.reorderDesktopTile(drag, null, ev.clientX, ev.clientY, rootGrid);
            } else {
                this.onDesktopAppDragEnd();
            }
        };
        this._onDesktopPointerCancel = () => {
            this._desktopPointerDrag = null;
            this.onDesktopAppDragEnd();
        };

        onMounted(() => {
            window.addEventListener("keydown", this._onGlobalKeydown);
            document.addEventListener("click", this._onDocumentClick, true);
            document.addEventListener("pointerdown", this._onDesktopPointerDown, true);
            document.addEventListener("pointermove", this._onDesktopPointerMove, true);
            document.addEventListener("pointerup", this._onDesktopPointerUp, true);
            document.addEventListener("pointercancel", this._onDesktopPointerCancel, true);
            this.loadScreenPreferences();
            this.loadDesktopPreferences();
        });

        onWillDestroy(() => {
            window.removeEventListener("keydown", this._onGlobalKeydown);
            document.removeEventListener("click", this._onDocumentClick, true);
            document.removeEventListener("pointerdown", this._onDesktopPointerDown, true);
            document.removeEventListener("pointermove", this._onDesktopPointerMove, true);
            document.removeEventListener("pointerup", this._onDesktopPointerUp, true);
            document.removeEventListener("pointercancel", this._onDesktopPointerCancel, true);
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
        const visibleApps = this.orderedApps;
        const q = (this.state.query || "").trim().toLowerCase();
        if (!q) {
            return visibleApps;
        }
        return visibleApps.filter((app) => (app.name || "").toLowerCase().includes(q));
    }

    get orderedApps() {
        return sortDesktopApps(
            this.visibleApps, this.state.sortMode, this.state.usageCounts,
            this.state.desktopItems, this.env.services.localization?.code || undefined
        );
    }

    get rootApps() {
        const folderByKey = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        return this.orderedApps.filter((app) => !folderByKey.get(this.appDesktopKey(app)) || this.isFavorite(app));
    }

    get desktopAppsToRender() {
        return this.state.query ? this.filteredApps : this.rootApps;
    }

    get desktopTilesToRender() {
        const appTiles = this.desktopAppsToRender.map((app) => ({
            kind: "app", app, key: `app:${this.appDesktopKey(app)}`, name: app.name || "Aplicación",
        }));
        if (this.state.query) return appTiles;
        const folderTiles = this.orderedFolders.map((folder) => ({
            kind: "folder", folder, key: `folder:${folder.id}`, name: folder.name || "Carpeta",
        }));
        const tiles = [...folderTiles, ...appTiles];
        let collator;
        try {
            collator = new Intl.Collator((this.env.services.localization?.code || "").replaceAll("_", "-"), { sensitivity: "base", numeric: true });
        } catch {
            collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
        }
        const favoriteKeys = new Set(this.rootApps.filter((app) => this.isFavorite(app)).map((app) => this.appDesktopKey(app)));
        const favoriteTiles = tiles.filter((tile) => tile.kind === "folder"
            ? Boolean(tile.folder.is_favorite)
            : favoriteKeys.has(this.appDesktopKey(tile.app)))
            .sort((a, b) => collator.compare(a.name, b.name));
        const remainingTiles = tiles.filter((tile) => tile.kind === "folder"
            ? !tile.folder.is_favorite
            : !favoriteKeys.has(this.appDesktopKey(tile.app)));
        if (this.state.sortMode === "custom") {
            const itemPositions = new Map(this.state.desktopItems.map((item, index) => [item.menu_key, Number(item.sequence ?? index)]));
            const folderPositions = new Map(this.state.desktopFolders.map((folder, index) => [folder.id, Number(folder.sequence ?? index)]));
            const position = (tile) => tile.kind === "folder"
                ? folderPositions.get(tile.folder.id) ?? Number.MAX_SAFE_INTEGER
                : itemPositions.get(this.appDesktopKey(tile.app)) ?? Number.MAX_SAFE_INTEGER;
            return [...favoriteTiles, ...remainingTiles.sort((a, b) => position(a) - position(b) || collator.compare(a.name, b.name))];
        }
        if (this.state.sortMode === "alphabetical") {
            return [...favoriteTiles, ...remainingTiles.sort((a, b) => collator.compare(a.name, b.name) || a.key.localeCompare(b.key))];
        }
        const appUsage = (app) => Number(this.state.usageCounts[this.appDesktopKey(app)] || 0);
        const folderUsage = (folder) => this.appsInFolder(folder).reduce((total, app) => total + appUsage(app), 0);
        const pinnedApps = [...this.rootApps].filter((app) => !favoriteKeys.has(this.appDesktopKey(app)))
            .sort((a, b) => appUsage(b) - appUsage(a) || collator.compare(a.name || "", b.name || ""))
            .slice(0, 3);
        const pinnedKeys = new Set(pinnedApps.map((app) => this.appDesktopKey(app)));
        const regularTiles = remainingTiles.filter((tile) => tile.kind === "folder" || !pinnedKeys.has(this.appDesktopKey(tile.app)));
        regularTiles.sort((a, b) => {
            const usageA = a.kind === "folder" ? folderUsage(a.folder) : appUsage(a.app);
            const usageB = b.kind === "folder" ? folderUsage(b.folder) : appUsage(b.app);
            return usageA - usageB || collator.compare(a.name, b.name);
        });
        return [...favoriteTiles, ...regularTiles, ...pinnedApps.map((app) => appTiles.find((tile) => tile.app.id === app.id)).filter(Boolean)];
    }

    get rootTileOrder() {
        return this.desktopTilesToRender.filter((tile) => !this.state.query).map((tile) => tile.key);
    }

    get orderedFolders() {
        const folders = [...this.state.desktopFolders];
        let collator;
        try {
            collator = new Intl.Collator((this.env.services.localization?.code || "").replaceAll("_", "-"), {
                sensitivity: "base", numeric: true,
            });
        } catch {
            collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
        }
        if (this.state.sortMode === "alphabetical") {
            return folders.sort((a, b) => collator.compare(a.name || "", b.name || "") || a.id - b.id);
        }
        if (this.state.sortMode === "most_used") {
            const usage = (folder) => this.appsInFolder(folder).reduce(
                (total, app) => total + Number(this.state.usageCounts[this.appDesktopKey(app)] || 0), 0
            );
            return folders.sort((a, b) => usage(b) - usage(a) || collator.compare(a.name || "", b.name || ""));
        }
        return folders.sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0) || a.id - b.id);
    }

    get openFolder() {
        return this.state.desktopFolders.find((folder) => folder.id === this.state.openFolderId) || null;
    }

    get folderEditorApps() {
        return this.orderedApps;
    }

    appsInFolder(folder) {
        const keys = new Set(this.state.desktopItems
            .filter((item) => item.folder_id === folder.id)
            .map((item) => item.menu_key));
        return this.orderedApps.filter((app) => keys.has(this.appDesktopKey(app)) && !this.isFavorite(app));
    }

    folderPreviewApps(folder) {
        return this.appsInFolder(folder).slice(0, 4);
    }

    onAppClick(app) {
        const pending = this._suppressDesktopClick;
        if (pending && pending.until >= Date.now() && pending.key === this.appDesktopKey(app)) {
            this._suppressDesktopClick = null;
            return;
        }
        this.selectApp(app);
    }

    get recentApps() {
        const byId = new Map(this.visibleApps.map((a) => [a.id, a]));
        if (this.state.recentKeys.length) {
            const byKey = new Map(this.visibleApps.map((app) => [this.appDesktopKey(app), app]));
            return this.state.recentKeys.map((key) => byKey.get(key)).filter(Boolean).slice(0, 8);
        }
        return this.state.recents.map((id) => byId.get(id)).filter(Boolean);
    }

    appDesktopKey(app) {
        return app.xmlid || `menu:${app.id}`;
    }

    get visibleApps() {
        return this.apps.filter((app) => !this.state.hiddenAppXmlids.includes(app.xmlid));
    }

    isFavorite(app) {
        return this.state.favorites.includes(app.id);
    }

    async toggleFavorite(app) {
        const favs = this.state.favorites;
        const next = favs.includes(app.id) ? favs.filter((id) => id !== app.id) : [...favs, app.id];
        this.state.favorites = next;
        this._saveJson("dolan_favorite_apps", next);
        const favoriteKeys = this.visibleApps
            .filter((item) => next.includes(item.id))
            .map((item) => this.appDesktopKey(item));
        try {
            await rpc("/dolan_theme/desktop/save_preferences", { values: { favorite_menu_keys: favoriteKeys } });
        } catch {
            this.notification.add("No se pudieron sincronizar los favoritos con tu usuario.", { type: "warning" });
        }
    }

    async toggleFolderFavorite(folder) {
        const current = this.state.desktopFolders.find((item) => item.id === folder.id);
        if (!current) return;
        const previous = current.is_favorite;
        current.is_favorite = !previous;
        try {
            await rpc("/dolan_theme/desktop/toggle_folder_favorite", {
                folder_id: current.id,
                is_favorite: current.is_favorite,
            });
        } catch {
            current.is_favorite = previous;
            this.notification.add("No se pudo guardar el favorito de la carpeta.", { type: "warning" });
        }
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
        this.loadDesktopPreferences();
        this.state.query = "";
        this.state.selectedIndex = -1;
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
        const loginThemeOverride = window.localStorage.getItem("dolan_login_theme_override");
        try {
            const response = await rpc("/dolan_theme/screen_preferences", {
                values: {
                    theme_mode: loginThemeOverride || (window.localStorage.getItem("dolan_dark_mode") === "1" ? "dark" : "light"),
                    compact_mode: window.localStorage.getItem("dolan_density") === "compact",
                },
            });
            this.state.darkMode = response.theme_mode === "dark";
            this.state.compact = Boolean(response.compact_mode);
            this.state.hiddenAppXmlids = response.hidden_app_xmlids || [];
            document.body.classList.toggle("o_dolan_dark_mode", this.state.darkMode);
            document.body.classList.toggle("o_dolan_compact", this.state.compact);
            window.localStorage.setItem("dolan_dark_mode", this.state.darkMode ? "1" : "0");
            if (loginThemeOverride && response.theme_mode === loginThemeOverride) {
                window.localStorage.removeItem("dolan_login_theme_override");
            }
            window.localStorage.setItem("dolan_density", this.state.compact ? "compact" : "normal");
            syncColorSchemeCookie(this.state.darkMode);
        } catch {
            // Conservar preferencias locales si el servidor no está disponible.
        }
    }

    async loadDesktopPreferences() {
        try {
            const data = await rpc("/dolan_theme/desktop/load", {});
            this.state.sortMode = data.sort_mode || "most_used";
            this.state.landingView = data.landing_view || "apps";
            this.state.showRecents = data.show_recents !== false;
            this.state.layoutVersion = Number(data.layout_version || 0);
            this.state.desktopItems = data.items || [];
            this.state.desktopFolders = data.folders || [];
            this.state.usageCounts = data.usage_counts || {};
            if (data.favorite_menu_keys === false || data.favorite_menu_keys === null || data.favorite_menu_keys === undefined) {
                const legacyIds = this.state.favorites.filter((id) => this.visibleApps.some((app) => app.id === id));
                this.state.favorites = legacyIds;
                const legacyKeys = this.visibleApps
                    .filter((app) => legacyIds.includes(app.id))
                    .map((app) => this.appDesktopKey(app));
                if (legacyKeys.length) {
                    await rpc("/dolan_theme/desktop/save_preferences", { values: { favorite_menu_keys: legacyKeys } });
                }
            } else {
                const favoriteKeys = new Set(data.favorite_menu_keys || []);
                this.state.favorites = this.visibleApps
                    .filter((app) => favoriteKeys.has(this.appDesktopKey(app)))
                    .map((app) => app.id);
                this._saveJson("dolan_favorite_apps", this.state.favorites);
            }
            this.state.recentKeys = data.recent_menu_keys || [];
            if (!this._desktopInitialApplied && this.state.isOpen) {
                this._desktopInitialApplied = true;
                this.setTab(this.state.landingView === "mine" ? "mine" : "apps");
            }
        } catch {
            // El launcher mantiene el modo alfabético y funciona con la caché local.
        }
    }

    async setDesktopSortMode(mode) {
        if (!["custom", "most_used", "alphabetical"].includes(mode)) return;
        this.state.sortMode = mode;
        try {
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: mode } });
        } catch {
            this.notification.add("No se pudo guardar el orden del escritorio.", { type: "warning" });
        }
    }

    async moveDesktopApp(app, offset) {
        if (this.state.sortMode !== "custom" || this.state.desktopLayoutSaving) return;
        const ordered = [...this.rootApps];
        const from = ordered.findIndex((item) => this.appDesktopKey(item) === this.appDesktopKey(app));
        const to = from + offset;
        if (from < 0 || to < 0 || to >= ordered.length) return;
        [ordered[from], ordered[to]] = [ordered[to], ordered[from]];
        await this.saveDesktopOrder(ordered);
    }

    onDesktopAppDragStart(app, ev, sourceFolderId = false) {
        if (this.state.sortMode !== "custom" || this.state.query) {
            ev.preventDefault();
            return;
        }
        this._desktopPointerDrag = null;
        this.state.desktopDraggingKey = this.appDesktopKey(app);
        this.state.desktopDraggingFolderId = sourceFolderId || false;
        ev.dataTransfer?.setData("text/plain", this.state.desktopDraggingKey);
        if (ev.dataTransfer) ev.dataTransfer.effectAllowed = "move";
    }

    onDesktopAppDragOver(ev, targetKey = null, targetFolderId = null) {
        if (this.state.desktopDraggingFolderKey && targetFolderId) {
            ev.preventDefault();
            this.state.desktopDropTargetFolderId = targetFolderId;
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
            return;
        }
        if (this.state.desktopDraggingKey) {
            ev.preventDefault();
            this.state.desktopDropTargetKey = targetKey;
            this.state.desktopDropTargetFolderId = targetFolderId;
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
        }
    }

    onRootDragOver(ev) {
        if (ev.target?.closest?.(".o_dolan_app_cell")) {
            ev.preventDefault();
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
            return;
        }
        this.onDesktopAppDragOver(ev);
    }

    onDesktopAppDragEnd() {
        this.state.desktopDraggingKey = null;
        this.state.desktopDraggingFolderId = null;
        this.state.desktopDropTargetKey = null;
        this.state.desktopDropTargetFolderId = null;
        this.state.desktopDraggingFolderKey = null;
        this.state.desktopPointerDropType = null;
    }

    async reorderFolderByDrop(sourceId, targetId, x, y, targetElement) {
        const folders = [...this.orderedFolders];
        const from = folders.findIndex((folder) => folder.id === sourceId);
        const to = folders.findIndex((folder) => folder.id === targetId);
        if (from < 0 || to < 0 || from === to) return this.onDesktopAppDragEnd();
        const rect = targetElement?.getBoundingClientRect?.();
        const after = rect ? (y > rect.top + rect.height / 2 || (Math.abs(y - rect.top - rect.height / 2) < rect.height / 4 && x > rect.left + rect.width / 2)) : true;
        const [moved] = folders.splice(from, 1);
        const insertAt = Math.max(0, Math.min(folders.length, to - (from < to ? 1 : 0) + (after ? 1 : 0)));
        folders.splice(insertAt, 0, moved);
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        this.onDesktopAppDragEnd();
        if (this.state.sortMode !== "custom") {
            this.state.sortMode = "custom";
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
        }
        await this.persistDesktopLayout(folders, assignment, this.rootApps.map((app) => this.appDesktopKey(app)));
    }

    async reorderDesktopTile(drag, targetTileKey, x, y, targetElement, { append = false } = {}) {
        if (this.state.desktopLayoutSaving || this.state.query) return this.onDesktopAppDragEnd();
        const order = [...(drag.rootTileOrder || this.rootTileOrder)];
        const sourceKey = drag.kind === "folder" ? `folder:${drag.folderId}` : `app:${drag.key}`;
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        if (drag.kind === "app" && drag.sourceFolderId) assignment.set(drag.key, false);
        const sourceIndex = order.indexOf(sourceKey);
        if (sourceIndex >= 0) order.splice(sourceIndex, 1);

        let insertAt = order.length;
        if (targetTileKey && targetTileKey !== sourceKey) {
            const targetIndex = order.indexOf(targetTileKey);
            if (targetIndex >= 0) {
                const rect = targetElement?.getBoundingClientRect?.();
                const before = rect ? (y < rect.top + rect.height / 2 ||
                    (Math.abs(y - rect.top - rect.height / 2) < rect.height / 4 && x < rect.left + rect.width / 2)) : true;
                insertAt = targetIndex + (before ? 0 : 1);
            }
        } else if (!append) {
            const candidates = [...document.querySelectorAll(".o_dolan_root_app_grid [data-desktop-tile-key]")]
                .filter((tile) => tile.dataset.desktopTileKey !== sourceKey)
                .map((tile) => {
                    const rect = tile.getBoundingClientRect();
                    return { tile, rect, distance: Math.hypot(x - (rect.left + rect.width / 2), y - (rect.top + rect.height / 2)) };
                }).sort((a, b) => a.distance - b.distance);
            const nearest = candidates[0];
            if (nearest) {
                const before = y < nearest.rect.top + nearest.rect.height / 2 ||
                    (Math.abs(y - nearest.rect.top - nearest.rect.height / 2) < nearest.rect.height / 4 && x < nearest.rect.left + nearest.rect.width / 2);
                insertAt = order.indexOf(nearest.tile.dataset.desktopTileKey) + (before ? 0 : 1);
            }
        }
        order.splice(Math.max(0, Math.min(insertAt, order.length)), 0, sourceKey);
        this.onDesktopAppDragEnd();
        if (this.state.sortMode !== "custom") {
            this.state.sortMode = "custom";
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
        }
        const rootOrderKeys = order.filter((key) => key.startsWith("app:") && !assignment.get(key.slice(4)))
            .map((key) => key.slice(4));
        await this.persistDesktopLayout(this.state.desktopFolders, assignment, rootOrderKeys, new Map(), order);
    }

    async dropAppAtRootPoint(drag, x, y, rootGrid) {
        const ordered = [...this.rootApps];
        const app = this.orderedApps.find((item) => this.appDesktopKey(item) === drag.key);
        if (!app) return this.onDesktopAppDragEnd();
        const candidates = [...rootGrid.querySelectorAll(".o_dolan_app_cell[data-menu-key]")]
            .filter((cell) => cell.dataset.menuKey !== drag.key)
            .map((cell) => {
                const rect = cell.getBoundingClientRect();
                return { key: cell.dataset.menuKey, rect, distance: Math.hypot(x - (rect.left + rect.width / 2), y - (rect.top + rect.height / 2)) };
            }).sort((a, b) => a.distance - b.distance);
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        assignment.set(drag.key, false);
        if (!candidates.length) ordered.push(app);
        else {
            const nearest = candidates[0];
            const before = y < nearest.rect.top + nearest.rect.height / 2 ||
                (Math.abs(y - nearest.rect.top - nearest.rect.height / 2) < nearest.rect.height / 4 && x < nearest.rect.left + nearest.rect.width / 2);
            let index = ordered.findIndex((item) => this.appDesktopKey(item) === nearest.key);
            if (!before) index += 1;
            const oldIndex = ordered.findIndex((item) => this.appDesktopKey(item) === drag.key);
            if (oldIndex >= 0 && oldIndex < index) index -= 1;
            if (oldIndex >= 0) ordered.splice(oldIndex, 1);
            ordered.splice(Math.max(0, Math.min(index, ordered.length)), 0, app);
        }
        this.onDesktopAppDragEnd();
        await this.persistDesktopLayout(this.state.desktopFolders, assignment, ordered.map((item) => this.appDesktopKey(item)));
    }

    async onDesktopAppDrop(app, ev, targetFolderId = false, rootTileOrder = this.rootTileOrder) {
        ev.preventDefault();
        const draggedKey = this.state.desktopDraggingKey || ev.dataTransfer?.getData("text/plain");
        const sourceFolderId = this.state.desktopDraggingFolderId;
        this.state.desktopDraggingKey = null;
        this.state.desktopDraggingFolderId = null;
        this.state.desktopDropTargetKey = null;
        this.state.desktopDropTargetFolderId = null;
        if (!draggedKey) return;
        if (this.state.sortMode !== "custom") {
            this.state.sortMode = "custom";
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
        }
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        if (targetFolderId) {
            if (sourceFolderId === targetFolderId) {
                const folder = this.state.desktopFolders.find((item) => item.id === targetFolderId);
                const orderedFolderApps = [...this.appsInFolder(folder)];
                const from = orderedFolderApps.findIndex((item) => this.appDesktopKey(item) === draggedKey);
                const to = app ? orderedFolderApps.findIndex((item) => this.appDesktopKey(item) === this.appDesktopKey(app)) : -1;
                if (from >= 0 && to >= 0 && from !== to) {
                    const [moved] = orderedFolderApps.splice(from, 1);
                    orderedFolderApps.splice(to, 0, moved);
                    await this.persistDesktopLayout(
                        this.state.desktopFolders, assignment,
                        this.rootApps.map((item) => this.appDesktopKey(item)),
                        new Map([[targetFolderId, orderedFolderApps.map((item) => this.appDesktopKey(item))]])
                    );
                }
                return;
            }
            assignment.set(draggedKey, targetFolderId);
            const nextTileOrder = rootTileOrder.filter((key) => key !== `app:${draggedKey}`);
            await this.persistDesktopLayout(
                this.state.desktopFolders, assignment,
                this.rootApps.filter((item) => this.appDesktopKey(item) !== draggedKey).map((item) => this.appDesktopKey(item)),
                new Map(), nextTileOrder
            );
            return;
        }
        if (sourceFolderId) {
            assignment.set(draggedKey, false);
            const orderedRoot = [...this.rootApps];
            const targetIndex = app ? orderedRoot.findIndex((item) => this.appDesktopKey(item) === this.appDesktopKey(app)) : orderedRoot.length;
            const sourceApp = this.orderedApps.find((item) => this.appDesktopKey(item) === draggedKey);
            if (sourceApp) orderedRoot.splice(Math.max(0, targetIndex), 0, sourceApp);
            await this.persistDesktopLayout(this.state.desktopFolders, assignment, orderedRoot.map((item) => this.appDesktopKey(item)));
            return;
        }
        const ordered = [...this.rootApps];
        const from = ordered.findIndex((item) => this.appDesktopKey(item) === draggedKey);
        const to = ordered.findIndex((item) => this.appDesktopKey(item) === this.appDesktopKey(app));
        if (from < 0 || to < 0 || from === to) return;
        const rect = ev.currentTarget?.getBoundingClientRect?.();
        const x = rect?.width ? (ev.clientX - rect.left) / rect.width : 0.5;
        const y = rect?.height ? (ev.clientY - rect.top) / rect.height : 0.5;
        if (x > 0.25 && x < 0.75 && y > 0.25 && y < 0.75) {
            this.openFolderEditor(null, [draggedKey, this.appDesktopKey(app)]);
            return;
        }
        const [moved] = ordered.splice(from, 1);
        ordered.splice(to, 0, moved);
        await this.saveDesktopOrder(ordered);
    }

    async onFolderDrop(folder, ev) {
        const draggedFolderId = this.state.desktopDraggingFolderKey;
        if (draggedFolderId) {
            await this.reorderFolderByDrop(draggedFolderId, folder.id, ev.clientX, ev.clientY, ev.currentTarget);
            return;
        }
        await this.onDesktopAppDrop(null, ev, folder.id);
    }

    onFolderDragStart(folder, ev) {
        if (this.state.query) {
            ev.preventDefault();
            return;
        }
        this._desktopPointerDrag = null;
        this.state.desktopDraggingKey = null;
        this.state.desktopDraggingFolderId = null;
        this.state.desktopDraggingFolderKey = folder.id;
        ev.dataTransfer?.setData("text/plain", `folder:${folder.id}`);
        if (ev.dataTransfer) ev.dataTransfer.effectAllowed = "move";
    }

    async onRootDrop(ev) {
        ev.preventDefault();
        const draggedFolderId = this.state.desktopDraggingFolderKey;
        if (draggedFolderId) {
            const folders = this.orderedFolders.filter((folder) => folder.id !== draggedFolderId);
            const draggedFolder = this.state.desktopFolders.find((folder) => folder.id === draggedFolderId);
            if (draggedFolder) folders.push(draggedFolder);
            const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
            this.onDesktopAppDragEnd();
            if (this.state.sortMode !== "custom") {
                this.state.sortMode = "custom";
                await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
            }
            if (draggedFolder) await this.persistDesktopLayout(folders, assignment, this.rootApps.map((item) => this.appDesktopKey(item)));
            return;
        }
        const key = this.state.desktopDraggingKey || ev.dataTransfer?.getData("text/plain");
        const sourceFolderId = this.state.desktopDraggingFolderId;
        this.state.desktopDraggingKey = null;
        this.state.desktopDraggingFolderId = null;
        this.state.desktopDropTargetKey = null;
        this.state.desktopDropTargetFolderId = null;
        if (!key) return;
        if (this.state.sortMode !== "custom") {
            this.state.sortMode = "custom";
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
        }
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        assignment.set(key, false);
        const app = this.orderedApps.find((item) => this.appDesktopKey(item) === key);
        const rootOrder = [...this.rootApps].filter((item) => this.appDesktopKey(item) !== key);
        if (app) rootOrder.push(app);
        await this.persistDesktopLayout(this.state.desktopFolders, assignment, rootOrder.map((item) => this.appDesktopKey(item)));
    }

    async removeAppFromFolder(app, folder) {
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        assignment.set(this.appDesktopKey(app), false);
        const rootOrder = [...this.rootApps, app].map((item) => this.appDesktopKey(item));
        await this.persistDesktopLayout(this.state.desktopFolders, assignment, rootOrder);
        this.state.openFolderId = folder.id;
    }

    async moveFolderApp(app, folder, offset) {
        if (this.state.desktopLayoutSaving) return;
        const ordered = [...this.appsInFolder(folder)];
        const from = ordered.findIndex((item) => this.appDesktopKey(item) === this.appDesktopKey(app));
        const to = from + offset;
        if (from < 0 || to < 0 || to >= ordered.length) return;
        [ordered[from], ordered[to]] = [ordered[to], ordered[from]];
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        await this.persistDesktopLayout(
            this.state.desktopFolders, assignment,
            this.rootApps.map((item) => this.appDesktopKey(item)),
            new Map([[folder.id, ordered.map((item) => this.appDesktopKey(item))]])
        );
    }

    async onFolderContentsDrop(folder, ev) {
        if (this.state.sortMode !== "custom") {
            this.state.sortMode = "custom";
            await rpc("/dolan_theme/desktop/save_preferences", { values: { sort_mode: "custom" } }).catch(() => {});
        }
        const dragged = this.state.desktopDraggingKey;
        const targetKey = ev.target?.closest?.("[data-menu-key]")?.dataset?.menuKey;
        const app = this.orderedApps.find((item) => this.appDesktopKey(item) === targetKey) || null;
        if (!targetKey && dragged && this.state.desktopDraggingFolderId === folder.id) {
            const ordered = [...this.appsInFolder(folder)];
            const from = ordered.findIndex((item) => this.appDesktopKey(item) === dragged);
            if (from >= 0) {
                const [moved] = ordered.splice(from, 1);
                ordered.push(moved);
                const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
                this.state.desktopDraggingKey = null;
                this.state.desktopDraggingFolderId = null;
                await this.persistDesktopLayout(this.state.desktopFolders, assignment,
                    this.rootApps.map((item) => this.appDesktopKey(item)),
                    new Map([[folder.id, ordered.map((item) => this.appDesktopKey(item))]]));
                return;
            }
        }
        await this.onDesktopAppDrop(app, ev, folder.id);
    }

    async saveDesktopOrder(apps) {
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        await this.persistDesktopLayout(this.state.desktopFolders, assignment, apps.map((app) => this.appDesktopKey(app)));
    }

    openDesktopFolder(folder) {
        this.state.openFolderId = folder.id;
    }

    closeDesktopFolder() {
        if (this.state.folderNameEditId) {
            this.commitFolderRename();
        }
        this.state.folderNameEditId = null;
        this.state.openFolderId = null;
    }

    startFolderRename(folder) {
        this.state.folderNameEditId = folder.id;
        this.state.folderNameDraft = folder.name || "";
        setTimeout(() => {
            const input = document.querySelector(".o_dolan_folder_rename_input");
            input?.focus();
            input?.select();
        }, 0);
    }

    onFolderRenameInput(ev) {
        this.state.folderNameDraft = ev.target.value;
    }

    onFolderRenameKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.target.blur();
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.state.folderNameEditId = null;
        }
    }

    async commitFolderRename() {
        const folderId = this.state.folderNameEditId;
        if (!folderId) return;
        const name = (this.state.folderNameDraft || "").trim();
        const current = this.state.desktopFolders.find((folder) => folder.id === folderId);
        this.state.folderNameEditId = null;
        if (!current || !name || name.length > 60 || name === current.name) return;

        const folders = this.state.desktopFolders.map((folder) =>
            folder.id === folderId ? { ...folder, name } : { ...folder }
        );
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        await this.persistDesktopLayout(
            folders,
            assignment,
            this.rootApps.map((app) => this.appDesktopKey(app)),
            new Map(),
            this.rootTileOrder
        );
    }

    stopFolderOverlayClick(ev) {
        ev.stopPropagation();
    }

    openFolderEditor(folder = null, selectedAppKeys = null) {
        const selected = selectedAppKeys || (folder ? this.appsInFolder(folder).map((app) => this.appDesktopKey(app)) : []);
        this.state.folderDraft = {
            id: folder?.id || false,
            client_key: folder ? String(folder.id) : `new-${Date.now()}`,
            name: folder?.name || "Nueva carpeta",
            selectedKeys: selected,
        };
    }

    setFolderPreset(kind) {
        const presets = {
            settings: { name: "Configuración", pattern: /ajustes?|configuraci[oó]n|settings?|base\.menu_management/i },
            sales: { name: "Ventas", pattern: /ventas?|sales|crm|contactos?|art[ií]culos|productos?|suscripciones?|alquiler/i },
            accounting: { name: "Contabilidad", pattern: /facturaci[oó]n|contabilidad|accounting|invoice|gastos?|compras?/i },
        };
        const preset = presets[kind];
        if (!preset || !this.state.folderDraft) return;
        const selectedKeys = this.orderedApps
            .filter((app) => preset.pattern.test(`${app.name || ""} ${app.xmlid || ""}`))
            .map((app) => this.appDesktopKey(app));
        this.state.folderDraft.name = preset.name;
        this.state.folderDraft.selectedKeys = selectedKeys;
    }

    toggleFolderDraftApp(app) {
        const key = this.appDesktopKey(app);
        const selected = this.state.folderDraft?.selectedKeys || [];
        this.state.folderDraft.selectedKeys = selected.includes(key)
            ? selected.filter((item) => item !== key)
            : [...selected, key];
    }

    updateFolderDraftName(ev) {
        if (this.state.folderDraft) this.state.folderDraft.name = ev.target.value;
    }

    async saveFolderDraft() {
        const draft = this.state.folderDraft;
        const name = (draft?.name || "").trim();
        if (!name || name.length > 60) {
            this.notification.add("El nombre debe tener entre 1 y 60 caracteres.", { type: "warning" });
            return;
        }
        const folders = this.state.desktopFolders.map((folder) => ({ ...folder }));
        let folder = folders.find((item) => item.id === draft.id);
        if (folder) folder.name = name;
        else {
            folder = { id: false, client_key: draft.client_key, name, sequence: folders.length * 10 + 10 };
            folders.push(folder);
        }
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        for (const app of this.orderedApps) {
            const key = this.appDesktopKey(app);
            if (draft.selectedKeys.includes(key)) assignment.set(key, folder.id || folder.client_key);
            else if (assignment.get(key) === folder.id) assignment.set(key, false);
        }
        const rootOrder = this.rootApps
            .filter((app) => !draft.selectedKeys.includes(this.appDesktopKey(app)))
            .map((app) => this.appDesktopKey(app));
        const ok = await this.persistDesktopLayout(folders, assignment, rootOrder);
        if (ok) {
            this.state.folderDraft = null;
            const saved = this.state.desktopFolders.find((item) => item.name === name);
            this.state.openFolderId = saved?.id || null;
        }
    }

    async deleteDesktopFolder(folder) {
        if (!window.confirm(`¿Eliminar la carpeta «${folder.name}»? Las aplicaciones volverán al escritorio.`)) return;
        const folders = this.state.desktopFolders.filter((item) => item.id !== folder.id);
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        for (const [key, folderId] of assignment) if (folderId === folder.id) assignment.set(key, false);
        const rootOrder = [...this.rootApps, ...this.appsInFolder(folder)].map((app) => this.appDesktopKey(app));
        if (await this.persistDesktopLayout(folders, assignment, rootOrder)) {
            this.state.openFolderId = null;
        }
    }

    async moveDesktopFolder(folder, offset) {
        if (this.state.sortMode !== "custom" || this.state.desktopLayoutSaving) return;
        const folders = [...this.orderedFolders];
        const from = folders.findIndex((item) => item.id === folder.id);
        const to = from + offset;
        if (from < 0 || to < 0 || to >= folders.length) return;
        [folders[from], folders[to]] = [folders[to], folders[from]];
        const assignment = new Map(this.state.desktopItems.map((item) => [item.menu_key, item.folder_id || false]));
        await this.persistDesktopLayout(folders, assignment, this.rootApps.map((item) => this.appDesktopKey(item)));
    }

    async persistDesktopLayout(folders, assignment, rootOrderKeys, folderOrders = new Map(), rootTileOrder = null) {
        if (this.state.desktopLayoutSaving) return false;
        const previousItems = this.state.desktopItems;
        const previousFolders = this.state.desktopFolders;
        const appsByKey = new Map(this.apps.map((app) => [this.appDesktopKey(app), app]));
        const allowedRootApps = new Set(rootOrderKeys.filter((key) => !assignment.get(key)));
        const folderKeyByToken = new Map(folders.map((folder) => [`folder:${folder.id || folder.client_key}`, folder.id || folder.client_key]));
        const tileOrder = rootTileOrder ? [...rootTileOrder] : [...this.rootTileOrder];
        const validTileOrder = tileOrder.filter((token, index) => {
            if (tileOrder.indexOf(token) !== index) return false;
            if (token.startsWith("app:")) return allowedRootApps.has(token.slice(4));
            return token.startsWith("folder:") && folderKeyByToken.has(token);
        });
        for (const folder of folders) {
            const token = `folder:${folder.id || folder.client_key}`;
            if (!validTileOrder.includes(token)) validTileOrder.push(token);
        }
        for (const key of rootOrderKeys) {
            const token = `app:${key}`;
            if (allowedRootApps.has(key) && !validTileOrder.includes(token)) validTileOrder.push(token);
        }
        const orderedKeys = [];
        const itemSequences = new Map();
        const folderSequences = new Map();
        for (const [index, token] of validTileOrder.entries()) {
            const tileSequence = (index + 1) * 1000;
            if (token.startsWith("app:")) {
                const key = token.slice(4);
                if (!orderedKeys.includes(key)) {
                    orderedKeys.push(key);
                    itemSequences.set(key, tileSequence);
                }
                continue;
            }
            const folderKey = folderKeyByToken.get(token);
            folderSequences.set(token, tileSequence);
            const explicitOrder = folderOrders.get(folderKey) || folderOrders.get(String(folderKey));
            const folderKeys = explicitOrder || this.orderedApps
                .filter((app) => assignment.get(this.appDesktopKey(app)) === folderKey)
                .map((app) => this.appDesktopKey(app));
            for (const [appIndex, key] of folderKeys.entries()) {
                if (assignment.get(key) === folderKey && !orderedKeys.includes(key)) {
                    orderedKeys.push(key);
                    itemSequences.set(key, tileSequence + appIndex + 1);
                }
            }
        }
        // Keep temporarily hidden or not currently rendered apps in their saved location.
        const known = new Set(orderedKeys);
        for (const item of [...previousItems].sort((a, b) => a.sequence - b.sequence)) {
            if (!known.has(item.menu_key) && appsByKey.has(item.menu_key)) {
                orderedKeys.push(item.menu_key);
                known.add(item.menu_key);
                itemSequences.set(item.menu_key, (validTileOrder.length + 1) * 1000 + orderedKeys.length);
                if (!assignment.has(item.menu_key)) assignment.set(item.menu_key, item.folder_id || false);
            }
        }
        const folderPayload = folders.map((folder, index) => ({
            id: folder.id || false,
            client_key: folder.client_key || String(folder.id),
            name: folder.name,
            sequence: folderSequences.get(`folder:${folder.id || folder.client_key}`) || (index + 1) * 1000,
        }));
        const items = orderedKeys.map((key, index) => ({
            menu_key: key,
            folder_id: assignment.get(key) || false,
            sequence: itemSequences.get(key) || (index + 1) * 10,
        }));
        this.state.desktopLayoutSaving = true;
        try {
            const response = await rpc("/dolan_theme/desktop/save_layout", {
                values: {
                    layout_version: this.state.layoutVersion,
                    folders: folderPayload,
                    items,
                },
            });
            if (response.status === "conflict") {
                this.notification.add("El escritorio cambió en otro dispositivo. Actualicé el orden guardado; volvé a mover la aplicación.", { type: "warning" });
                await this.loadDesktopPreferences();
                return false;
            }
            this.state.layoutVersion = response.layout_version;
            this.state.desktopItems = items;
            this.state.desktopFolders = folders.map((folder, index) => ({
                id: folder.id || response.folder_ids?.[folder.client_key] || false,
                name: folder.name,
                sequence: folderSequences.get(`folder:${folder.id || folder.client_key}`) || folder.sequence || (index + 1) * 1000,
            }));
            await this.loadDesktopPreferences();
            return true;
        } catch {
            this.state.desktopItems = previousItems;
            this.state.desktopFolders = previousFolders;
            this.notification.add("No se pudo guardar el orden personalizado.", { type: "danger" });
            return false;
        } finally {
            this.state.desktopLayoutSaving = false;
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
        if (tab === "workspace") tab = "mine";
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
        this.state.selectedIndex = -1;
    }

    onKeydown(ev) {
        const list = this.filteredApps;
        if (!list.length) {
            return;
        }
        const cols = window.innerWidth >= 768 ? 6 : 4;
        if (ev.key === "ArrowRight") {
            ev.preventDefault();
            this.state.selectedIndex = this.state.selectedIndex < 0 ? 0 : (this.state.selectedIndex + 1) % list.length;
        } else if (ev.key === "ArrowLeft") {
            ev.preventDefault();
            this.state.selectedIndex = this.state.selectedIndex < 0 ? list.length - 1 : (this.state.selectedIndex - 1 + list.length) % list.length;
        } else if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.selectedIndex = this.state.selectedIndex < 0 ? 0 : Math.min(list.length - 1, this.state.selectedIndex + cols);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.selectedIndex = this.state.selectedIndex < 0 ? 0 : Math.max(0, this.state.selectedIndex - cols);
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
        rpc("/dolan_theme/desktop/record_open", { menu_key: this.appDesktopKey(app) })
            .then(() => this.loadDesktopPreferences())
            .catch(() => {});
        this.closeDrawer({ restore: false });
        this.menuService.selectMenu(app);
    }
}

registry.category("systray").add(
    "DOLAN_theme.AppDrawerSystray",
    { Component: DolanAppDrawerSystray },
    { sequence: 100 }
);
