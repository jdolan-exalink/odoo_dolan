/** @odoo-module **/
// Part of DOLAN Suite for Odoo 20 CE. See LICENSE file for full copyright and licensing details.
// License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import { Component, onPatched, proxy, signal } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useBus, useService } from "@web/core/utils/hooks";

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

    messageBlocks(content) {
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
                this.state.messages = res.events || [];
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
        this.state.isOpen = false;
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "dolan.ai.provider",
            res_id: this.state.provider.id || false,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    async onModelSelect(ev) {
        const newModel = ev.target.value;
        this.state.provider.model = newModel;
        try {
            await rpc("/dolan_ai/chat/set_model", { model: newModel });
        } catch (err) {
            console.error("Error actualizando modelo de IA:", err);
        }
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

        try {
            const ctx = this.currentContext;
            const result = await rpc("/dolan_ai/chat/send", {
                message: text,
                session_id: this.state.sessionId,
                agent_id: this.state.agent.id,
                res_model: ctx.resModel,
                res_id: ctx.resId,
                smart_action: smartAction,
            });
            if (result) {
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
                if (result.dashboard_action) {
                    await this.actionService.doAction(result.dashboard_action);
                }
                if (result.workflow_action) {
                    await this.actionService.doAction(result.workflow_action);
                }
            }
        } catch (err) {
            this.state.messages.push({
                id: Date.now() + 2,
                role: "assistant",
                content: "No pude procesar el mensaje. Revisá tu conexión e intentá de nuevo.",
            });
        } finally {
            this.state.isLoading = false;
        }
    }
}

export const dolanAiSystrayItem = {
    Component: DolanAiSystray,
};

registry.category("systray").add("DOLAN_ai.AskAiSystray", dolanAiSystrayItem, { sequence: 15 });
