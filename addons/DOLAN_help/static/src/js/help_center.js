/** @odoo-module **/

import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { router } from "@web/core/browser/router";
import { useService } from "@web/core/utils/hooks";

/** Texto de la ayuda a HTML: escapa todo y solo permite **negrita**, `código` y los números (1) de las capturas. */
export function formatHelpText(text) {
    const escaped = String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    return markup(
        escaped
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/`(.+?)`/g, "<code>$1</code>")
            .replace(/\((\d{1,2})\)/g, '<span class="o_dolan_help_marker">$1</span>')
    );
}

/** Saca acentos y pasa a minúsculas, para buscar «facturacion» y encontrar «Facturación». */
export function normalizeText(text) {
    return String(text || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();
}

/** Busca en el índice: todas las palabras tienen que aparecer; pesa más el título. */
export function searchHelp(index, query, limit = 30) {
    const words = normalizeText(query).split(/\s+/).filter((w) => w.length > 1);
    if (!words.length) {
        return [];
    }
    const results = [];
    for (const row of index || []) {
        const title = normalizeText(row.title);
        const haystack = `${title} ${normalizeText(row.where)} ${normalizeText(row.text)}`;
        if (!words.every((w) => haystack.includes(w))) {
            continue;
        }
        let score = 0;
        for (const w of words) {
            if (title.includes(w)) {
                score += title.startsWith(w) ? 6 : 4;
            } else {
                score += 1;
            }
        }
        if (row.ref.startsWith("app:")) {
            score += 1;
        }
        results.push({ ...row, score });
    }
    results.sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));
    return results.slice(0, limit);
}

export class DolanHelpCenter extends Component {
    static template = "DOLAN_help.HelpCenter";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.menu = useService("menu");
        this.formatHelpText = formatHelpText;
        this.state = proxy({
            loading: true,
            error: false,
            index: null,
            ref: "",
            page: null,
            query: "",
            results: [],
            zoom: null,
            feedback: null,
            feedbackComment: "",
        });
        onWillStart(async () => {
            await this.loadIndex();
            const params = this.props.action?.params || {};
            const initial =
                params.ref ||
                (params.view === "company" && params.id ? `company:${params.id}` : "") ||
                router.current.ref ||
                new URLSearchParams(window.location.search).get("ref") ||
                "";
            await this.go(initial, { replace: true });
        });
    }

    async loadIndex() {
        try {
            this.state.index = await this.orm.call("dolan.help.center", "get_index", []);
            this.state.error = false;
        } catch {
            this.state.error = true;
        }
        this.state.loading = false;
    }

    /** Abre una página de la ayuda: "", "app:clave", "folder:clave", "sector:clave", "sector:clave/slug", "company:id", "app/slug". */
    async go(ref, { replace = false } = {}) {
        ref = ref || "";
        this.state.zoom = null;
        this.state.feedback = null;
        this.state.feedbackComment = "";
        let page = { type: "home" };
        if (ref.startsWith("app:")) {
            const app = this.state.index?.apps[ref.slice(4)] || this.state.index?.general.find((g) => g.key === ref.slice(4));
            page = app ? { type: "app", app } : { type: "missing" };
        } else if (ref.startsWith("folder:")) {
            const folder = this.state.index?.folders.find((f) => f.key === ref.slice(7));
            page = folder ? { type: "folder", folder } : { type: "missing" };
        } else if (ref === "sectors") {
            page = { type: "sectors" };
        } else if (ref === "apps") {
            page = { type: "apps" };
        } else if (ref.startsWith("sector:") && !ref.includes("/")) {
            const sector = this.state.index?.sectors.find((s) => s.key === ref.slice(7));
            page = sector ? { type: "sector", sector } : { type: "missing" };
        } else if (ref.startsWith("sector:") || ref.startsWith("company:")) {
            const data = await this.orm.call("dolan.help.center", "get_procedure", [ref]);
            page = data.error ? { type: "missing" } : { type: data.kind === "company" ? "company" : "procedure", data };
            if (data.kind === "company") {
                data.body = markup(data.body || "");
            }
        } else if (ref.includes("/")) {
            const data = await this.orm.call("dolan.help.center", "get_task", [ref]);
            page = data.error ? { type: data.error === "no_access" ? "noaccess" : "missing" } : { type: "task", data };
        }
        this.state.ref = ref;
        this.state.page = page;
        this.state.query = "";
        this.state.results = [];
        router.pushState({ ref: ref || undefined }, { replace });
        document.querySelector(".o_dolan_help")?.scrollTo({ top: 0 });
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value;
        this.state.results = searchHelp(this.state.index?.search, this.state.query);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter" && this.state.results.length) {
            this.go(this.state.results[0].ref);
        } else if (ev.key === "Escape") {
            this.state.query = "";
            this.state.results = [];
        }
    }

    appOf(key) {
        return this.state.index?.apps[key];
    }

    breadcrumbs() {
        const page = this.state.page;
        const crumbs = [{ label: "Ayuda", ref: "" }];
        if (!page) {
            return crumbs;
        }
        if (page.type === "folder" || page.type === "apps") {
            crumbs.push({ label: "Por aplicación", ref: "apps" });
        } else if (page.type === "app") {
            const app = page.app;
            if (app.folder) {
                crumbs.push({ label: app.folder_name, ref: `folder:${app.folder}` });
            }
        } else if (page.type === "task") {
            const app = this.appOf(page.data.app_key);
            if (app) {
                crumbs.push({ label: app.folder_name, ref: `folder:${app.folder}` });
            }
            crumbs.push({ label: page.data.app_name, ref: `app:${page.data.app_key}` });
        } else if (page.type === "sector" || page.type === "sectors") {
            crumbs.push({ label: "Por sector", ref: "sectors" });
        } else if (page.type === "procedure" || page.type === "company") {
            crumbs.push({ label: "Por sector", ref: "sectors" });
            const sector = this.state.index?.sectors.find((s) => s.name === page.data.sector);
            if (sector) {
                crumbs.push({ label: sector.name, ref: `sector:${sector.key}` });
            }
        }
        return crumbs;
    }

    openApp(app) {
        if (app?.menu_id) {
            this.menu.selectMenu(app.menu_id);
        }
    }

    shareLink() {
        const url = `${window.location.origin}/ayuda/${this.state.ref}`;
        navigator.clipboard?.writeText(url).then(
            () => this.notification.add("Link copiado. Pegalo en WhatsApp o en un correo.", { type: "success" }),
            () => this.notification.add(url, { title: "Link de este artículo", sticky: true })
        );
    }

    setZoom(url) {
        this.state.zoom = url;
    }

    setFeedbackComment(ev) {
        this.state.feedbackComment = ev.target.value;
    }

    print() {
        window.print();
    }

    editCompany(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dolan.help.article",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    newCompanyArticle(sectorId = false) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dolan.help.article",
            views: [[false, "form"]],
            target: "current",
            context: sectorId ? { default_sector_id: sectorId } : {},
        });
    }

    newSector() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Nuevo sector",
            res_model: "dolan.help.sector",
            views: [[false, "form"]],
            target: "new",
        }, { onClose: () => this.loadIndex().then(() => this.go("sectors", { replace: true })) });
    }

    async sendFeedback(useful) {
        const page = this.state.page;
        const title = page?.data?.title || "";
        if (useful) {
            await this.orm.call("dolan.help.center", "send_feedback", [this.state.ref, title, true, ""]);
            this.state.feedback = "thanks";
        } else {
            this.state.feedback = "ask";
        }
    }

    async sendFeedbackComment() {
        const title = this.state.page?.data?.title || "";
        await this.orm.call("dolan.help.center", "send_feedback", [this.state.ref, title, false, this.state.feedbackComment]);
        this.state.feedback = "thanks";
    }
}

registry.category("actions").add("dolan_help_center", DolanHelpCenter);
