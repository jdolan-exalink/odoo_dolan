/** @odoo-module **/

const THEME_KEY = "dolan_dark_mode";
const LOGIN_OVERRIDE_KEY = "dolan_login_theme_override";

function readThemePreference() {
    const mode = window.localStorage.getItem("dolan_theme_mode");
    if (mode === "dark") return true;
    if (mode === "light") return false;
    if (mode === "system") return Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches);
    const localValue = window.localStorage.getItem(THEME_KEY);
    if (localValue === "1") return true;
    if (localValue === "0") return false;

    const cookieValue = document.cookie
        .split(";")
        .map((value) => value.trim())
        .find((value) => value.startsWith("color_scheme="))
        ?.split("=", 2)[1];
    if (cookieValue === "dark") return true;
    return Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches);
}

function applyTheme(isDark, saveChoice = false) {
    document.body.classList.toggle("o_dolan_dark_mode", isDark);
    document.documentElement.style.colorScheme = isDark ? "dark" : "light";
    window.localStorage.setItem(THEME_KEY, isDark ? "1" : "0");
    if (isDark) {
        document.cookie = "color_scheme=dark;path=/;max-age=31536000;SameSite=Lax";
    } else {
        document.cookie = "color_scheme=;path=/;max-age=0;SameSite=Lax";
    }
    if (saveChoice) {
        // The authenticated preference endpoint will persist this choice after login.
        window.localStorage.setItem(LOGIN_OVERRIDE_KEY, isDark ? "dark" : "light");
        window.localStorage.setItem("dolan_theme_mode", isDark ? "dark" : "light");
    }

    const button = document.querySelector("[data-dolan-theme-toggle]");
    if (button) {
        const nextLabel = isDark ? "Modo claro" : "Modo oscuro";
        button.setAttribute("aria-label", `Cambiar a ${nextLabel.toLowerCase()}`);
        button.setAttribute("aria-pressed", String(isDark));
        button.title = `Cambiar a ${nextLabel.toLowerCase()}`;
    }
}

function initializeLoginTheme() {
    if (!document.body.classList.contains("o_web_login")) return;
    let isDark = readThemePreference();
    applyTheme(isDark);
    const systemTheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    systemTheme?.addEventListener?.("change", (event) => {
        if (window.localStorage.getItem("dolan_theme_mode") === "system") applyTheme(event.matches);
    });
    document.addEventListener("click", (event) => {
        if (!event.target.closest("[data-dolan-theme-toggle]")) return;
        isDark = !isDark;
        applyTheme(isDark, true);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeLoginTheme, { once: true });
} else {
    initializeLoginTheme();
}
