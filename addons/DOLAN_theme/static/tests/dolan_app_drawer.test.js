import { expect, test } from "@odoo/hoot";

import { shouldHandleAppDrawerKeydown, sortDesktopApps } from "@DOLAN_theme/js/dolan_app_drawer";

const apps = [
    { id: 1, xmlid: "base.menu_sales", name: "Ventas" },
    { id: 2, xmlid: "base.menu_contacts", name: "Contactos" },
    { id: 3, xmlid: "base.menu_calendar", name: "Calendario" },
];

test("AI composer is excluded from app drawer global keyboard handling", () => {
    const chat = document.createElement("section");
    chat.className = "o_dolan_ai_drawer";
    const textarea = document.createElement("textarea");
    chat.append(textarea);

    const appSearch = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(textarea, appSearch)).toBe(false);
});

test("app drawer search keeps its own keyboard handling", () => {
    const appSearch = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(appSearch, appSearch)).toBe(true);
});

test("other editable fields are excluded from app drawer global keyboard handling", () => {
    const formInput = document.createElement("input");
    expect(shouldHandleAppDrawerKeydown(formInput, null)).toBe(false);
});

test("alphabetical order uses translated names and a stable tie break", () => {
    expect(sortDesktopApps(apps, "alphabetical").map((app) => app.id)).toEqual([3, 2, 1]);
});

test("Odoo locale codes with underscores do not break the app drawer", () => {
    expect(sortDesktopApps(apps, "alphabetical", {}, [], "es_AR").map((app) => app.id)).toEqual([3, 2, 1]);
});

test("most used order uses observed counts and alphabetical ties", () => {
    const sorted = sortDesktopApps(apps, "most_used", {
        "base.menu_sales": 4,
        "base.menu_contacts": 4,
        "base.menu_calendar": 0,
    });
    expect(sorted.map((app) => app.id)).toEqual([2, 1, 3]);
});

test("custom order is preserved and newly installed apps are appended alphabetically", () => {
    const sorted = sortDesktopApps(apps, "custom", {}, [
        { menu_key: "base.menu_sales", sequence: 20 },
        { menu_key: "base.menu_contacts", sequence: 10 },
    ]);
    expect(sorted.map((app) => app.id)).toEqual([2, 1, 3]);
});
