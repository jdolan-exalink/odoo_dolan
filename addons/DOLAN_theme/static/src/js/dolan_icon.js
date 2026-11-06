/** @odoo-module **/

import { Component, t, useProps } from "@odoo/owl";

/**
 * Iconos SVG propios (24x24, trazo). No dependen de Font Awesome ni de ninguna fuente
 * externa, por lo que se ven igual en todos los navegadores y en la PWA offline.
 */
const CIRCLE = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z";
export const DOLAN_ICON_PATHS = {
    search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M21 21l-4.3-4.3"],
    "x-circle": [CIRCLE, "M15 9l-6 6", "M9 9l6 6"],
    grid: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
    folder: ["M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M3 9h18"],
    "folder-plus": ["M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2", "M3 9h11", "M16 16h6", "M19 13v6", "M3 9v9a2 2 0 0 0 2 2h8"],
    "sort-az": ["M4 5h7", "M4 9h5", "M4 13h3", "M17 4v16", "M14 17l3 3 3-3"],
    home: ["M3 10.5L12 3l9 7.5", "M5 9.5V21h14V9.5", "M9 21v-6h6v6"],
    dashboard: ["M3 13a9 9 0 0 1 18 0", "M12 13l4-4", "M3 13h2", "M19 13h2"],
    bolt: ["M13 2L4 14h7l-1 8 9-12h-7z"],
    clock: [CIRCLE, "M12 7v5l3 2"],
    check: ["M5 12l5 5L20 7"],
    compress: ["M4 14h6v6", "M20 10h-6V4", "M14 10l7-7", "M3 21l7-7"],
    history: ["M3 12a9 9 0 1 0 3-6.7L3 8", "M3 3v5h5", "M12 7v5l3 2"],
    star: ["M12 3l2.9 5.9 6.5.9-4.7 4.6 1.1 6.5L12 17.8 6.2 20.9l1.1-6.5L2.6 9.8l6.5-.9z"],
    "file-text": [
        "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z",
        "M14 3v5h5", "M9 13h6", "M9 17h6",
    ],
    cart: ["M3 4h2l2.4 11h10.2L20 7H6", "M9 20h.01", "M17 20h.01"],
    "user-plus": [
        "M15 20v-1a5 5 0 0 0-5-5H7a5 5 0 0 0-5 5v1",
        "M8.5 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M19 8v6", "M16 11h6",
    ],
    money: ["M3 6h18v12H3z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M6 12h.01", "M18 12h.01"],
    chat: ["M21 12a8 8 0 0 1-11.8 7L4 20.5l1.6-4.8A8 8 0 1 1 21 12z"],
    bank: ["M3 10l9-6 9 6", "M5 10v8", "M9.5 10v8", "M14.5 10v8", "M19 10v8", "M3 21h18"],
    sparkles: [
        "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z",
        "M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
    ],
    sun: [
        "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M12 2v2", "M12 20v2", "M4.9 4.9l1.4 1.4",
        "M17.7 17.7l1.4 1.4", "M2 12h2", "M20 12h2", "M4.9 19.1l1.4-1.4", "M17.7 6.3l1.4-1.4",
    ],
    moon: ["M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"],
    "alert-triangle": [
        "M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
        "M12 9v4", "M12 17h.01",
    ],
    "alert-circle": [CIRCLE, "M12 8v4", "M12 16h.01"],
    calendar: ["M4 6h16v14H4z", "M4 10h16", "M8 3v4", "M16 3v4"],
    pencil: ["M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19z", "M14 7l3 3"],
    truck: ["M2 6h12v10H2z", "M14 10h4l4 3v3h-8z", "M7 19h.01", "M18 19h.01"],
    factory: ["M3 21V9l6 4V9l6 4V5h6v16z"],
    wrench: ["M14.7 6.3a4 4 0 0 0 5 5l-9.4 9.4a2.1 2.1 0 0 1-3-3z"],
    tasks: ["M9 6h12", "M9 12h12", "M9 18h12", "M3 6l1 1 2-2", "M3 12l1 1 2-2", "M3 18l1 1 2-2"],
};

/** Nombres heredados de Font Awesome (p. ej. los que envía el servidor) -> icono propio. */
const ALIASES = {
    "fa-exclamation-triangle": "alert-triangle",
    "fa-exclamation-circle": "alert-circle",
    "fa-calendar": "calendar",
    "fa-pencil": "pencil",
    "fa-clock-o": "clock",
    "fa-file-text-o": "file-text",
    "fa-money": "money",
    "fa-shopping-cart": "cart",
    "fa-truck": "truck",
    "fa-industry": "factory",
    "fa-wrench": "wrench",
    "fa-tasks": "tasks",
};

export class DolanIcon extends Component {
    static template = "DOLAN_theme.Icon";

    props = useProps({
        name: t.string(),
        size: t.number().optional(),
        filled: t.boolean().optional(),
    });

    get paths() {
        const key = ALIASES[this.props.name] || this.props.name;
        return DOLAN_ICON_PATHS[key] || DOLAN_ICON_PATHS.bolt;
    }

    get size() {
        return this.props.size || 18;
    }
}
