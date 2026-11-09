import { expect, test } from "@odoo/hoot";

import { DolanAiSystray, normalizeStructuredReply } from "@DOLAN_ai/js/ai_systray";

test("structured JSON replies render as readable Spanish bullets", () => {
    const result = normalizeStructuredReply('{"records":[{"display_name":"Cliente Demo","amount_total":1250,"invoice_date":"2026-11-01"}]}');
    expect(result).toBe("**Registros**\n- **Cliente Demo** — Importe: 1250; Fecha: 2026-11-01");
});

test("JSON prose and non-JSON AI answers remain readable", () => {
    expect(normalizeStructuredReply('{"reply":"Encontré dos facturas."}')).toBe("Encontré dos facturas.");
    expect(normalizeStructuredReply("El saldo es **positivo**.")).toBe("El saldo es **positivo**.");
});

test("JSON wrapped by the Odoo AI status prefix renders as readable Spanish", () => {
    const result = normalizeStructuredReply('Resultado procesado por Odoo AI:\n{"status":"ok","lines":[{"account_id":1216,"debit:sum":1250,"credit:sum":500,"balance:sum":750}]}');
    expect(result).toBe("**Estado:** ok\n\n**Líneas**\n- **Cuenta 1216** — Débitos: 1250; Créditos: 500; Saldo: 750");
});

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
