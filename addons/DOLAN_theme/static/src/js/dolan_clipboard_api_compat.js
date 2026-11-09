/*
 * Odoo's web_tour clipboard helper reads navigator.clipboard.writeText at
 * module evaluation time. Chromium does not expose navigator.clipboard on
 * ordinary HTTP LAN origins, so provide its expected API before that helper
 * loads. This keeps the app usable on local demo deployments without TLS.
 */
(function () {
    const current = window.navigator.clipboard;
    if (typeof current?.writeText === "function") {
        return;
    }

    const clipboard = current || {};
    clipboard.writeText = function (value) {
        return new Promise((resolve, reject) => {
            if (!document.body || typeof document.execCommand !== "function") {
                reject(new DOMException("Clipboard unavailable", "NotAllowedError"));
                return;
            }
            const textarea = document.createElement("textarea");
            textarea.value = String(value ?? "");
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);
            const copied = document.execCommand("copy");
            textarea.remove();
            if (copied) {
                resolve();
            } else {
                reject(new DOMException("Clipboard write was denied", "NotAllowedError"));
            }
        });
    };

    try {
        Object.defineProperty(window.navigator, "clipboard", {
            configurable: true,
            value: clipboard,
        });
    } catch {
        // The property can be readonly in some browser builds. In that case
        // web_tour will still receive the existing API if the browser exposed it.
    }
})();
