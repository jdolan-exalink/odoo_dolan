/** @odoo-module **/

import { ErrorDialog, RPCErrorDialog } from "@web/core/errors/error_dialogs";
import { patch } from "@web/core/utils/patch";

function errorText(dialog) {
    const props = dialog.props || {};
    return [
        props.name,
        props.message,
        props.contextDetails,
        dialog.traceback || props.traceback,
    ].filter((part) => typeof part === "string" && part.trim()).join("\n\n");
}

async function copyText(text) {
    const clipboard = globalThis.navigator?.clipboard;
    if (typeof clipboard?.writeText === "function") {
        await clipboard.writeText(text);
        return true;
    }

    // Clipboard API is unavailable on ordinary HTTP LAN origins. Keep the
    // error dialog usable there with the synchronous legacy browser fallback.
    if (!globalThis.document?.body || typeof document.execCommand !== "function") {
        return false;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.inset = "0 auto auto 0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
        copied = document.execCommand("copy");
    } finally {
        textarea.remove();
    }
    return copied;
}

async function onClickClipboard() {
    try {
        const copied = await copyText(errorText(this));
        if (copied && typeof this.showTooltip === "function") {
            this.showTooltip();
        }
    } catch {
        // Copying diagnostics must never replace the original Odoo error with
        // a second exception (for example on HTTP without Clipboard API).
    }
}

patch(ErrorDialog.prototype, { onClickClipboard });
// RPCErrorDialog overrides the core handler, so patch that prototype too.
patch(RPCErrorDialog.prototype, { onClickClipboard });
