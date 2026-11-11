/** @odoo-module **/
// Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
// License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import { Component, onPatched, proxy, signal } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useBus, useService } from "@web/core/utils/hooks";

const JSON_FIELD_LABELS = {
    company: "Empresa", period: "Período", count: "Cantidad", total: "Total",
    currency: "Moneda", status: "Estado", summary: "Resumen", records: "Registros",
    name: "Nombre", display_name: "Nombre", amount_total: "Importe", invoice_date: "Fecha",
    lines: "Líneas",
    account_id: "Cuenta", "debit:sum": "Débitos", "credit:sum": "Créditos", "balance:sum": "Saldo",
};

function extractJsonPayload(source) {
    const fenced = source.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i)?.[1];
    const text = fenced || source;
    const start = Math.min(...[text.indexOf("{"), text.indexOf("[")].filter((index) => index >= 0));
    if (!Number.isFinite(start)) return null;
    const stack = [];
    let inString = false;
    let escaped = false;
    for (let index = start; index < text.length; index++) {
        const char = text[index];
        if (inString) {
            if (escaped) escaped = false;
            else if (char === "\\") escaped = true;
            else if (char === '"') inString = false;
            continue;
        }
        if (char === '"') inString = true;
        else if (char === "{" || char === "[") stack.push(char);
        else if (char === "}" || char === "]") {
            const opening = stack.pop();
            if ((opening === "{" && char !== "}") || (opening === "[" && char !== "]")) return null;
            if (!stack.length) return text.slice(start, index + 1);
        }
    }
    return null;
}

function readableJsonValue(value) {
    if (value === null || value === undefined || value === false || value === "") return "Sin informar";
    if (Array.isArray(value)) return value.map(readableJsonValue).join(", ");
    if (typeof value === "object") {
        return Object.entries(value).map(([key, item]) => {
            const label = JSON_FIELD_LABELS[key] || key.replaceAll("_", " ");
            return `${label}: ${readableJsonValue(item)}`;
        }).join("; ");
    }
    return String(value);
}

export function normalizeStructuredReply(content) {
    const source = String(content || "").trim();
    const candidate = extractJsonPayload(source);
    if (!candidate) return content || "";
    let data;
    try {
        data = JSON.parse(candidate);
    } catch {
        return content || "";
    }
    if (typeof data === "string") return data;
    if (data && !Array.isArray(data)) {
        const prose = data.reply || data.summary || data.message || data.response;
        if (typeof prose === "string" && prose.trim()) return prose;
    }
    const rows = Array.isArray(data) ? data : [data];
    if (rows.every((row) => row && typeof row === "object" && !Array.isArray(row))) {
        const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
        const identityKey = keys.find((key) => ["display_name", "name", "number", "ref", "account_id"].includes(key));
        if (identityKey) {
            return rows.map((row, index) => {
                const identity = identityKey === "account_id" ? `Cuenta ${row[identityKey]}` : row[identityKey] || `Registro ${index + 1}`;
                const details = Object.entries(row)
                    .filter(([key, value]) => key !== identityKey && key !== "id" && value !== null && value !== false)
                    .map(([key, value]) => `${JSON_FIELD_LABELS[key] || key.replaceAll("_", " ")}: ${readableJsonValue(value)}`);
                return `- **${readableJsonValue(identity)}**${details.length ? ` — ${details.join("; ")}` : ""}`;
            }).join("\n");
        }
    }
    if (data && !Array.isArray(data)) {
        return Object.entries(data).map(([key, value]) => {
            const label = JSON_FIELD_LABELS[key] || key.replaceAll("_", " ");
            if (Array.isArray(value) && value.every((row) => row && typeof row === "object")) {
                return `**${label}**\n${normalizeStructuredReply(JSON.stringify(value))}`;
            }
            return `**${label}:** ${readableJsonValue(value)}`;
        }).join("\n\n");
    }
    return `**Resultado**\n${readableJsonValue(data)}`;
}

const RECOVERY_POLL_MS = 4000;
const RECOVERY_MAX_MS = 120000;

function newClientRequestId() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }
    return `req-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

/**
 * Clasifica un error de rpc() sin depender de imports internos de Odoo.
 * - "server": Odoo respondió con un error (UserError, AccessError, etc.).
 * - "connection": no hubo respuesta JSON válida: corte de red, proxy o túnel
 *   (502, 520, 524 de Cloudflare). Odoo pudo haber terminado igual.
 */
export function classifyRpcError(err) {
    const serverMessage = err?.data?.message || (err?.name === "RPC_ERROR" ? err?.message : "");
    if (serverMessage) {
        return { kind: "server", message: serverMessage };
    }
    const text = String(err?.message || "");
    if (
        err?.constructor?.name === "ConnectionLostError" ||
        err?.name === "ConnectionLostError" ||
        /couldn't be established|interrupted|connection|network|failed to fetch/i.test(text)
    ) {
        return { kind: "connection", message: "" };
    }
    return { kind: "server", message: text || "error inesperado en el navegador." };
}

export class DolanAiSystray extends Component {
    static template = "DOLAN_ai.DolanAiSystray";

    chatBody = signal.ref();
    composerInput = signal.ref();

    setup() {
        this.actionService = useService("action");
        useBus(this.env.bus, "DOLAN:TOGGLE_AI_CHAT", () => this.toggleDrawer());
        useBus(this.env.bus, "DOLAN:CLOSE_AI_CHAT", () => this.closeDrawer());
        this.state = proxy({
            isOpen: false,
            isMinimized: false,
            isMaximized: false,
            showSidebar: false,
            isLoading: false,
            isRecording: false,
            isTranscribing: false,
            isBootstrapping: false,
            bootstrapped: false,
            sessionId: null,
            agent: {
                id: null,
                name: "Odoo AI",
                subtitle: "Tu copiloto empresarial para el día a día en Odoo 20.",
            },
            provider: {
                name: "ChatGPT plan (Sign in with ChatGPT)",
                mode: "chatgpt_oauth",
                model: "gpt-6.1-sol",
                oauth_status: "disconnected",
            },
            availableModels: [],
            messages: [],
            sessions: [],
            promptButtons: [],
            smartActions: [],
            inputText: "",
            uiError: "",
        });
        this._focusComposerAfterOpen = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        onPatched(() => {
            const chatBody = this.chatBody();
            if (this.state.isOpen && chatBody) {
                chatBody.scrollTop = chatBody.scrollHeight;
            }
            if (this.state.isOpen && this._focusComposerAfterOpen) {
                const composer = this.composerInput();
                if (composer) {
                    composer.focus();
                    this._focusComposerAfterOpen = false;
                }
            }
        });
    }

    get currentContext() {
        const controller = this.actionService?.currentController;
        const props = controller?.props || {};
        return {
            resModel: props.resModel || null,
            resId: props.resId || null,
        };
    }

    get currentTitle() {
        const firstUserMessage = this.state.messages.find((msg) => msg.role === "user");
        return firstUserMessage?.content || "Conversación actual";
    }

    messageBlocks(content, role = "assistant") {
        // Only assistant replies are reshaped; JSON typed by the user stays verbatim.
        if (role !== "user") {
            content = normalizeStructuredReply(content);
        }
        const blocks = [];
        let paragraph = [];
        let listItems = [];
        let code = null;
        const flushParagraph = () => {
            if (paragraph.length) {
                blocks.push({ type: "text", content: paragraph.join("\n") });
                paragraph = [];
            }
        };
        const flushList = () => {
            if (listItems.length) {
                blocks.push({ type: "list", items: listItems });
                listItems = [];
            }
        };
        for (const line of (content || "").split(/\r?\n/)) {
            const fence = line.match(/^\s*```([\w+-]*)\s*$/);
            if (fence) {
                if (code) {
                    blocks.push({ type: "code", content: code.lines.join("\n"), language: code.language });
                    code = null;
                } else {
                    flushList();
                    flushParagraph();
                    code = { language: fence[1], lines: [] };
                }
            } else if (code) {
                code.lines.push(line);
            } else if (/^\s*#{1,6}\s+/.test(line)) {
                flushList();
                flushParagraph();
                blocks.push({ type: "heading", content: line.replace(/^\s*#{1,6}\s+/, "") });
            } else if (/^\s*[-*]\s+/.test(line)) {
                flushParagraph();
                listItems.push(line.replace(/^\s*[-*]\s+/, ""));
            } else if (line.trim()) {
                flushList();
                paragraph.push(line);
            } else {
                flushList();
                flushParagraph();
            }
        }
        if (code) {
            blocks.push({ type: "code", content: code.lines.join("\n"), language: code.language });
        }
        flushList();
        flushParagraph();
        return blocks.length ? blocks : [{ type: "text", content: content || "" }];
    }

    inlineMessageParts(content) {
        const parts = [];
        const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((?:\/[^)\s]*|https:\/\/[^)\s]+)\))/g;
        let cursor = 0;
        for (const match of (content || "").matchAll(pattern)) {
            if (match.index > cursor) {
                parts.push({ type: "text", content: content.slice(cursor, match.index) });
            }
            if (match[0].startsWith("[")) {
                const link = match[0].match(/^\[([^\]]+)\]\(([^)]+)\)$/);
                if (link && (link[2].startsWith("/") || link[2].startsWith("https://"))) {
                    parts.push({ type: "link", content: link[1], href: link[2] });
                } else {
                    parts.push({ type: "text", content: match[0] });
                }
            } else {
                const isBold = match[0].startsWith("**");
                parts.push({
                    type: isBold ? "bold" : "inline_code",
                    content: isBold ? match[0].slice(2, -2) : match[0].slice(1, -1),
                });
            }
            cursor = match.index + match[0].length;
        }
        if (cursor < (content || "").length) {
            parts.push({ type: "text", content: content.slice(cursor) });
        }
        return parts.length ? parts : [{ type: "text", content: content || "" }];
    }

    async toggleDrawer() {
        if (this.state.isMinimized) {
            this.state.isMinimized = false;
            this.state.isOpen = true;
            this._focusComposerAfterOpen = true;
        } else if (this.state.isOpen) {
            this.state.isOpen = false;
            this.state.isMinimized = true;
            this._focusComposerAfterOpen = false;
        } else {
            this.state.isOpen = true;
            this.state.isMinimized = false;
            this._focusComposerAfterOpen = true;
            if (!this.state.bootstrapped) {
                await this.bootstrapChat();
            } else if (!this.state.isLoading) {
                // Las acciones rápidas dependen del registro abierto ahora,
                // no del que estaba abierto la primera vez.
                await this.bootstrapChat(this.state.sessionId);
            }
        }
    }

    minimizeDrawer() {
        this.state.isOpen = false;
        this.state.isMinimized = true;
        this._focusComposerAfterOpen = false;
    }

    restoreFromMinimized() {
        this.state.isMinimized = false;
        this.state.isOpen = true;
        this._focusComposerAfterOpen = true;
    }

    closeMinimized() {
        this.state.isMinimized = false;
        this.state.isOpen = false;
        this._focusComposerAfterOpen = false;
    }

    closeDrawer() {
        this.state.isOpen = false;
        this.state.isMinimized = false;
        this.state.showSidebar = false;
        this._focusComposerAfterOpen = false;
    }

    toggleMaximize() {
        this.state.isMaximized = !this.state.isMaximized;
        if (!this.state.isMaximized) {
            this.state.showSidebar = false;
        }
    }

    toggleSidebar() {
        this.state.showSidebar = !this.state.showSidebar;
    }

    onInputText(ev) {
        this.state.inputText = ev.target.value;
    }

    async bootstrapChat(sessionId = null) {
        this.state.isLoading = true;
        this.state.isBootstrapping = true;
        this.state.uiError = "";
        try {
            const ctx = this.currentContext;
            const res = await rpc("/dolan_ai/chat/bootstrap", {
                interface_key: "systray_ai_button",
                res_model: ctx.resModel,
                res_id: ctx.resId,
                session_id: sessionId,
            });
            if (res) {
                this.state.agent = res.agent || this.state.agent;
                this.state.provider = res.provider || this.state.provider;
                this.state.availableModels = res.provider?.available_models || [];
                this.state.sessionId = res.session_id || null;
                this.state.messages = (res.events || []).map((event) => ({
                    ...event,
                    usedFallback: Boolean(event.used_fallback),
                    fallbackReason: event.fallback_reason || "",
                }));
                this.state.sessions = res.sessions || [];
                this.state.promptButtons = res.prompt_buttons || [];
                this.state.smartActions = (res.smart_actions || []).map((code) => ({
                    code,
                    label: code === "draft_collection" ? "Redactar cobranza" : "Resumir Chatter",
                    prompt: code === "draft_collection"
                        ? "Redactá un mensaje cordial y profesional para solicitar el pago de esta factura pendiente. No lo envíes."
                        : "Resumí el hilo de Chatter del registro abierto en puntos breves. Separá hechos, pedidos y próximos pasos.",
                }));
                this.state.bootstrapped = true;
            }
        } catch (err) {
            console.error("Error inicializando DOLAN Ask AI:", err);
            this.state.uiError = "No se pudo cargar el chat. Actualizá la página y volvé a intentarlo.";
        } finally {
            this.state.isLoading = false;
            this.state.isBootstrapping = false;
        }
    }

    onInputKeydown(ev) {
        // The theme registers a window-level key handler for the app drawer.
        // Typing in the composer must never bubble into global app search.
        ev.stopPropagation();
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    async toggleVoiceInput() {
        if (this.state.isTranscribing) {
            return;
        }
        if (this.state.isRecording) {
            this.mediaRecorder?.stop();
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
            this.state.uiError = "Este navegador no permite grabar audio. Probá con un navegador actualizado.";
            return;
        }
        try {
            this.state.uiError = "";
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
                .find((type) => MediaRecorder.isTypeSupported?.(type));
            this.audioChunks = [];
            this.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data?.size) {
                    this.audioChunks.push(event.data);
                }
            };
            this.mediaRecorder.onstop = async () => {
                stream.getTracks().forEach((track) => track.stop());
                this.state.isRecording = false;
                const audio = new Blob(this.audioChunks, { type: this.mediaRecorder?.mimeType || "audio/webm" });
                if (audio.size) {
                    await this.transcribeVoiceInput(audio);
                }
                this.mediaRecorder = null;
                this.audioChunks = [];
            };
            this.mediaRecorder.start();
            this.state.isRecording = true;
        } catch (err) {
            this.state.isRecording = false;
            this.state.uiError = err?.name === "NotAllowedError"
                ? "Permití el acceso al micrófono para usar el dictado."
                : "No se pudo iniciar la grabación de audio.";
        }
    }

    async transcribeVoiceInput(audio) {
        this.state.isTranscribing = true;
        this.state.uiError = "";
        try {
            const extension = audio.type.includes("mp4") ? "m4a" : "webm";
            const dataUrl = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result || "").split(",").pop());
                reader.onerror = () => reject(new Error("No se pudo leer el audio grabado."));
                reader.readAsDataURL(audio);
            });
            const result = await rpc("/dolan_ai/chat/transcribe", {
                audio_base64: dataUrl,
                filename: `dictado.${extension}`,
                content_type: audio.type || "audio/webm",
            });
            if (result.error) {
                throw new Error(result.error);
            }
            if (result.text) {
                this.state.inputText = [this.state.inputText.trim(), result.text.trim()].filter(Boolean).join(" ");
                this._focusComposerAfterOpen = true;
            }
        } catch (err) {
            this.state.uiError = err?.message || "No se pudo transcribir el audio.";
        } finally {
            this.state.isTranscribing = false;
        }
    }

    async sendPromptButton(btn) {
        const promptText = btn.prompt || btn.name;
        await this.sendMessage(promptText, btn.name);
    }

    async sendSmartAction(action) {
        await this.sendMessage(action.prompt, action.label, action.code);
    }

    async startNewConversation() {
        this.state.sessionId = null;
        this.state.messages = [];
        this.state.uiError = "";
        this.state.inputText = "";
        this.closeSidebar();
        this._focusComposerAfterOpen = true;
    }

    closeSidebar() {
        this.state.showSidebar = false;
    }

    async openConversation(session) {
        if (!session) {
            return;
        }
        this.closeSidebar();
        if (session.id === this.state.sessionId) {
            return;
        }
        await this.bootstrapChat(session.id);
    }

    async deleteConversation(session, ev) {
        ev?.stopPropagation();
        if (!session || !window.confirm(`¿Borrar la conversación “${session.name}”?`)) {
            return;
        }
        try {
            await rpc("/dolan_ai/chat/delete", { session_id: session.id });
            this.state.sessions = this.state.sessions.filter((item) => item.id !== session.id);
            if (this.state.sessionId === session.id) {
                this.state.sessionId = null;
                this.state.messages = [];
                this.state.inputText = "";
                this._focusComposerAfterOpen = true;
            }
        } catch (err) {
            console.error("Error borrando conversación DOLAN AI:", err);
            this.state.uiError = "No se pudo borrar la conversación. Actualizá la vista e intentá de nuevo.";
        }
    }

    async openOAuthConfig() {
        const provider = this.state.provider;
        const canConfigure = Boolean(provider.can_change_model);
        if (canConfigure && provider.oauth_status !== "connected") {
            // Sin conexión lista: el asistente guía proveedor, clave y modelo.
            await this.openConnectionWizard();
            return;
        }
        this.state.isOpen = false;
        await this.actionService.doAction("DOLAN_ai.action_dolan_ai_provider");
    }

    async openConnectionWizard() {
        await this.actionService.doAction("DOLAN_ai.action_dolan_ai_connection_wizard", {
            onClose: () => this.bootstrapChat(this.state.sessionId),
        });
    }

    async onModelSelect(ev) {
        const newModel = ev.target.value;
        const previousModel = this.state.provider.model;
        this.state.provider.model = newModel;
        try {
            const result = await rpc("/dolan_ai/chat/set_model", { model: newModel });
            if (result?.status !== "ok") {
                this.state.provider.model = previousModel;
                ev.target.value = previousModel;
                this.state.uiError = result?.error || "No se pudo cambiar el modelo de IA.";
            }
        } catch (err) {
            console.error("Error actualizando modelo de IA:", err);
            this.state.provider.model = previousModel;
            ev.target.value = previousModel;
            this.state.uiError = "No se pudo cambiar el modelo de IA.";
        }
    }

    /**
     * Después de un corte del proxy o túnel, consulta si Odoo guardó la
     * respuesta del pedido. Devuelve el resultado o null si no apareció.
     */
    async recoverReply(clientRequestId) {
        const started = Date.now();
        while (Date.now() - started < RECOVERY_MAX_MS) {
            await new Promise((resolve) => setTimeout(resolve, RECOVERY_POLL_MS));
            try {
                const result = await rpc("/dolan_ai/chat/recover", { client_request_id: clientRequestId });
                if (result?.status === "done") {
                    return result;
                }
                if (result?.session_id && !this.state.sessionId) {
                    this.state.sessionId = result.session_id;
                }
            } catch (err) {
                if (classifyRpcError(err).kind === "server") {
                    return null;
                }
                // Sigue sin conexión: se vuelve a intentar hasta el límite.
            }
        }
        return null;
    }

    pushAssistantResult(result) {
        this.state.sessionId = result.session_id || this.state.sessionId;
        if (result.session_id) {
            const recent = { id: result.session_id, name: result.session_name || this.currentTitle };
            this.state.sessions = [recent, ...this.state.sessions.filter((session) => session.id !== result.session_id)].slice(0, 30);
        }
        this.state.messages.push({
            id: result.event_id || Date.now() + 1,
            role: "assistant",
            content: result.reply || "",
            usedFallback: Boolean(result.used_fallback),
            fallbackReason: result.fallback_reason || "",
        });
    }

    async sendMessage(overridePrompt = null, displayLabel = null, smartAction = null) {
        const rawText = overridePrompt !== null ? overridePrompt : this.state.inputText;
        const text = (rawText || "").trim();
        if (!text || this.state.isLoading) {
            return;
        }
        if (overridePrompt === null) {
            this.state.inputText = "";
        }
        this.state.uiError = "";

        this.state.messages.push({
            id: Date.now(),
            role: "user",
            content: displayLabel || text,
        });
        this.state.isLoading = true;
        const clientRequestId = newClientRequestId();

        try {
            const ctx = this.currentContext;
            const result = await rpc("/dolan_ai/chat/send", {
                message: text,
                session_id: this.state.sessionId,
                agent_id: this.state.agent.id,
                res_model: ctx.resModel,
                res_id: ctx.resId,
                smart_action: smartAction,
                client_request_id: clientRequestId,
            });
            if (result) {
                this.pushAssistantResult(result);
                if (result.dashboard_action) {
                    await this.actionService.doAction(result.dashboard_action);
                }
                if (result.workflow_action) {
                    await this.actionService.doAction(result.workflow_action);
                }
            }
        } catch (err) {
            const error = classifyRpcError(err);
            if (error.kind === "server") {
                this.state.messages.push({
                    id: Date.now() + 2,
                    role: "assistant",
                    content: `No pude completar el pedido: ${error.message}`,
                });
            } else {
                // El túnel o proxy cortó la conexión (por ejemplo 502, 520 o
                // 524). Odoo puede seguir trabajando: esperamos su respuesta.
                this.state.uiError = "Se cortó la conexión con el servidor. Estoy esperando la respuesta…";
                const recovered = await this.recoverReply(clientRequestId);
                this.state.uiError = "";
                if (recovered) {
                    this.pushAssistantResult(recovered);
                } else {
                    this.state.messages.push({
                        id: Date.now() + 2,
                        role: "assistant",
                        content: "Se cortó la conexión con el servidor y no recibí la respuesta. Puede ser un corte del proxy o del túnel; reintentá en un momento.",
                    });
                }
            }
        } finally {
            this.state.isLoading = false;
        }
    }
}

export const dolanAiSystrayItem = {
    Component: DolanAiSystray,
};

registry.category("systray").add("DOLAN_ai.AskAiSystray", dolanAiSystrayItem, { sequence: 15 });
