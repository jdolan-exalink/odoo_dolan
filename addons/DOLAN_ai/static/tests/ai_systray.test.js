import { expect, test } from "@odoo/hoot";

import { DolanAiSystray } from "@DOLAN_ai/js/ai_systray";

function dispatchComposerKey(key, shiftKey = false) {
    const chat = document.createElement("section");
    chat.className = "o_dolan_ai_drawer";
    const textarea = document.createElement("textarea");
    chat.append(textarea);

    let reachedWindow = false;
    let sendCount = 0;
    const onWindowKeydown = () => {
        reachedWindow = true;
    };
    window.addEventListener("keydown", onWindowKeydown);
    textarea.addEventListener("keydown", (event) => {
        DolanAiSystray.prototype.onInputKeydown.call(
            { sendMessage: () => { sendCount += 1; } },
            event
        );
    });

    const event = new KeyboardEvent("keydown", {
        bubbles: true,
        cancelable: true,
        key,
        shiftKey,
    });
    textarea.dispatchEvent(event);
    window.removeEventListener("keydown", onWindowKeydown);

    return { event, reachedWindow, sendCount };
}

test("typing in the AI composer does not bubble to app search", () => {
    const result = dispatchComposerKey("a");
    expect(result.reachedWindow).toBe(false);
    expect(result.sendCount).toBe(0);
});

test("Enter sends once without bubbling to app search", () => {
    const result = dispatchComposerKey("Enter");
    expect(result.reachedWindow).toBe(false);
    expect(result.event.defaultPrevented).toBe(true);
    expect(result.sendCount).toBe(1);
});

test("Shift+Enter keeps the newline path and does not send", () => {
    const result = dispatchComposerKey("Enter", true);
    expect(result.reachedWindow).toBe(false);
    expect(result.event.defaultPrevented).toBe(false);
    expect(result.sendCount).toBe(0);
});
