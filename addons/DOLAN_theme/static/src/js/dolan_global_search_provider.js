/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { DefaultCommandItem } from "@web/core/commands/command_palette";
import { syncColorSchemeCookie } from "./dolan_app_drawer";

const commandProviderRegistry = registry.category("command_provider");
const commandCategoryRegistry = registry.category("command_categories");

// 1. Categorías visuales organizadas para la Command Palette
if (!commandCategoryRegistry.contains("dolan_quick_actions")) {
    commandCategoryRegistry.add("dolan_quick_actions", {
        name: _t("⚡ Acciones Rápidas"),
        sequence: 10,
    });
}
if (!commandCategoryRegistry.contains("dolan_contacts")) {
    commandCategoryRegistry.add("dolan_contacts", {
        name: _t("👤 Contactos (Clientes / Proveedores)"),
        sequence: 20,
    });
}
if (!commandCategoryRegistry.contains("dolan_products")) {
    commandCategoryRegistry.add("dolan_products", {
        name: _t("📦 Productos"),
        sequence: 30,
    });
}
if (!commandCategoryRegistry.contains("dolan_invoices")) {
    commandCategoryRegistry.add("dolan_invoices", {
        name: _t("📄 Facturación y Asientos"),
        sequence: 40,
    });
}
if (!commandCategoryRegistry.contains("dolan_sales")) {
    commandCategoryRegistry.add("dolan_sales", {
        name: _t("🛒 Ventas y Presupuestos"),
        sequence: 50,
    });
}

// 2. Proveedor de Acciones Rápidas (Siempre disponible al abrir Ctrl+K)
commandProviderRegistry.add("dolan_quick_actions", {
    provide(options) {
        const actionService = useService("action");
        const menuService = useService("menu");

        const quickActions = [
            {
                name: _t("Nueva Factura de Cliente"),
                action: () => actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "account.move",
                    views: [[false, "form"]],
                    context: { default_move_type: "out_invoice" },
                }),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Nuevo Presupuesto de Venta"),
                action: () => actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "sale.order",
                    views: [[false, "form"]],
                }),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Nuevo Contacto (Cliente / Proveedor)"),
                action: () => actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "res.partner",
                    views: [[false, "form"]],
                }),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Registrar Pago / Cobranza"),
                action: () => actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "account.payment",
                    views: [[false, "form"]],
                }),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Bandeja de Mensajes WhatsApp"),
                action: () => actionService.doAction("DOLAN_whatsapp.action_dolan_whatsapp_messages"),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Libro IVA Digital y SICORE (ARCA)"),
                action: () => actionService.doAction("DOLAN_l10n_ar_afip.action_l10n_ar_libro_iva_digital_wizard"),
                category: "dolan_quick_actions",
            },
            {
                name: _t("Alternar Modo Claro / Oscuro"),
                action: () => {
                    const isDark = document.body.classList.toggle("o_dolan_dark_mode");
                    window.localStorage.setItem("dolan_dark_mode", isDark ? "1" : "0");
                    syncColorSchemeCookie(isDark);
                },
                category: "dolan_quick_actions",
            },
        ];

        const search = (options.searchValue || "").toLowerCase().trim();
        return quickActions
            .filter((item) => !search || item.name.toLowerCase().includes(search))
            .map((item) => ({
                Component: DefaultCommandItem,
                action: item.action,
                category: item.category,
                name: item.name,
                props: {},
            }));
    },
});

// 3. Proveedor de Búsqueda Global Universal (Contactos, Productos, Facturas, Ventas)
commandProviderRegistry.add("dolan_global_search", {
    async provide(options) {
        const query = (options.searchValue || "").trim();
        if (query.length < 2) {
            return [];
        }

        const actionService = useService("action");

        try {
            const data = await rpc("/dolan_theme/search_global", { query, limit: 5 });
            const results = data.results || [];

            return results.map((item) => {
                let cat = "default";
                if (item.category === "contact") cat = "dolan_contacts";
                else if (item.category === "product") cat = "dolan_products";
                else if (item.category === "invoice") cat = "dolan_invoices";
                else if (item.category === "sale") cat = "dolan_sales";

                return {
                    Component: DefaultCommandItem,
                    action: () => {
                        actionService.doAction({
                            type: "ir.actions.act_window",
                            res_model: item.model,
                            res_id: item.res_id,
                            views: [[false, "form"]],
                        });
                    },
                    category: cat,
                    name: `${item.name} (${item.subtitle})`,
                    props: {},
                };
            });
        } catch (e) {
            console.warn("[DOLAN Global Search] Error en búsqueda universal:", e);
            return [];
        }
    },
});
