import { expect, test } from "@odoo/hoot";

import { shouldHandleAppDrawerKeydown } from "@DOLAN_theme/js/dolan_app_drawer";

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
