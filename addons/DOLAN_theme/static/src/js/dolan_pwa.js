/** @odoo-module **/

// Registro del Service Worker para PWA
if ("serviceWorker" in navigator && window.location.protocol.startsWith("http")) {
    window.addEventListener("load", () => {
        navigator.serviceWorker
            .register("/dolan_theme/sw.js", { scope: "/" })
            .then((registration) => {
                console.log("[DOLAN PWA] Service Worker registrado con éxito en scope:", registration.scope);
            })
            .catch((error) => {
                console.warn("[DOLAN PWA] No se pudo registrar el Service Worker:", error);
            });
    });
}
