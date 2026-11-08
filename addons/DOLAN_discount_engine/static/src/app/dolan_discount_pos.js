import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { formatCurrency } from "@web/core/currency";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

function asDate(value) {
    if (!value) return null;
    const text = String(value).replace(" ", "T");
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(text) ? text : `${text}Z`);
}

function localParts(date, timezone) {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: timezone || "America/Argentina/Buenos_Aires",
        weekday: "short", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return {
        weekday: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].indexOf(values.weekday),
        date: `${values.year}-${values.month}-${values.day}`,
        hour: Number(values.hour) + Number(values.minute) / 60 + Number(values.second) / 3600,
    };
}

function campaignIsActive(campaign, now) {
    const snapshot = campaign.snapshot || {};
    const start = asDate(snapshot.date_start);
    const end = asDate(snapshot.date_end);
    if (!start || !end || now < start || now > end) return false;
    const local = localParts(now, snapshot.timezone);
    if ((snapshot.excluded_dates || []).includes(local.date)) return false;
    if ((snapshot.weekday_ids || []).length && !snapshot.weekday_ids.includes(local.weekday)) return false;
    return local.hour >= (snapshot.time_start || 0) && local.hour < (snapshot.time_end ?? 24);
}

function proposalForLine(line, now, paymentMethodId = false) {
    const campaigns = line.pos?.config?.dolan_discount_campaigns || line.config?.dolan_discount_campaigns || [];
    const product = line.product_id;
    const qty = Math.max(0, Number(line.qty || 0));
    const base = Math.max(0, qty * Number(line.price_unit || 0));
    const rounding = Number(line.currency?.rounding || line.pos?.currency?.rounding || 0.01);
    if (!product || !qty || !base) return [];

    const candidates = [];
    const partner = line.order_id?.partner_id;
    for (const campaign of campaigns) {
        const snapshot = campaign.snapshot || {};
        if (!campaignIsActive(campaign, now)) continue;
        for (const rule of snapshot.rules || []) {
            if ((rule.payment_method_id && Number(rule.payment_method_id) !== Number(paymentMethodId)) || qty < Number(rule.min_qty || 0)) continue;
            if (rule.product_ids?.length && !rule.product_ids.includes(product.id)) continue;
            if (rule.excluded_product_ids?.includes(product.id)) continue;
            if (rule.partner_ids?.length && (!partner || !rule.partner_ids.includes(partner.id))) continue;
            if (rule.partner_category_ids?.length) {
                const categoryIds = partner?.category_id?.map((category) => category.id) || [];
                if (!categoryIds.some((id) => rule.partner_category_ids.includes(id))) continue;
            }
            if (rule.category_ids?.length) {
                let category = product.categ_id;
                let matches = false;
                while (category) {
                    if (rule.category_ids.includes(category.id)) {
                        matches = true;
                        break;
                    }
                    category = category.parent_id;
                }
                if (!matches) continue;
            }
            candidates.push({ campaign, rule });
        }
    }
    candidates.sort((a, b) =>
        Number(b.rule.priority || 0) - Number(a.rule.priority || 0) ||
        Number(b.campaign.snapshot.priority || 0) - Number(a.campaign.snapshot.priority || 0) ||
        a.campaign.id - b.campaign.id || a.rule.rule_id - b.rule.rule_id
    );

    const selected = [];
    for (const candidate of candidates) {
        if (!selected.length || (candidate.rule.stackable && selected.every((item) => item.rule.stackable))) {
            selected.push(candidate);
        } else {
            break;
        }
    }

    let remaining = base;
    return selected.flatMap(({ campaign, rule }) => {
        let rawAmount;
        if (rule.benefit_type === "percent") {
            rawAmount = base * Number(rule.benefit_value || 0) / 100;
        } else if (rule.benefit_type === "special_price") {
            rawAmount = Math.max(0, Number(line.price_unit || 0) - Number(rule.benefit_value || 0)) * qty;
        } else if (rule.benefit_type === "second_unit") {
            const buy = Math.max(0, Number(rule.buy_qty || 0));
            const get = Math.max(0, Number(rule.get_qty || 0));
            const block = buy + get;
            const bundles = block ? Math.floor(qty / block) : 0;
            const remainder = Math.max(0, qty - bundles * block - buy);
            const discountedQty = bundles * get + Math.min(get, remainder);
            rawAmount = discountedQty * Number(line.price_unit || (base / qty)) * Number(rule.second_unit_percent || 0) / 100;
        } else {
            rawAmount = qty * Number(rule.benefit_value || 0);
        }
        const cappedAmount = Math.min(rawAmount, Number(rule.max_discount_amount || rawAmount), remaining);
        const amount = Math.max(0, Math.round(cappedAmount / rounding + Number.EPSILON) * rounding);
        remaining = Math.max(0, remaining - amount);
        if (!amount) return [];
        return [{
            line_uuid: line.uuid,
            product_id: product.id,
            campaign_id: campaign.id,
            rule_id: rule.rule_id,
            campaign_version: campaign.version,
            base_amount: base,
            eligible_payment_ratio: 1,
            discount_amount: amount,
            rule_snapshot: rule,
        }];
    });
}

patch(Orderline.prototype, {
    get lineScreenValues() {
        const values = super.lineScreenValues;
        const applications = this.line.dolan_discount_applications || [];
        return {
            ...values,
            dolanPromotions: applications.map((application) => ({
                name: application.rule_snapshot?.name || "Promoción",
                amount: formatCurrency(application.discount_amount, this.line.currency.id),
            })),
        };
    },
});

patch(PosOrderline.prototype, {
    setDiscount(discount) {
        const isCampaignUpdate = this._dolanCampaignUpdate;
        const result = super.setDiscount(...arguments);
        if (!isCampaignUpdate) {
            this.dolan_discount_base_percent = this.discount || 0;
            this.dolan_discount_applications = [];
            this.dolan_discount_approval_uuid = false;
            this.dolan_discount_employee_token = false;
            this.dolan_discount_employee_applications = [];
            this.dolan_discount_employee_percent = 0;
        }
        return result;
    },
});

patch(PosStore.prototype, {
    async authorizeDolanPromotions(order, paymentMethodId = false) {
        if (!order || order.state !== "draft") return;
        if (!navigator.onLine) {
            const hadBenefits = order.getOrderlines().some(
                (line) => line.dolan_discount_applications?.length || Number(line.dolan_discount_base_percent || 0) || line.dolan_discount_employee_token
            );
            if (hadBenefits) {
                this.notification.add(
                    "Se perdió la conexión. Conservamos la orden y sus descuentos, pero no se puede iniciar ni confirmar el cobro hasta reconectar. No vuelvas a cobrar desde la terminal; al volver la red, verificá su estado y sincronizá esta misma orden.",
                    { type: "danger", sticky: true }
                );
                return false;
            }
            // An order without server-authorized discounts may continue through
            // Odoo's standard offline POS queue.
            return true;
        }
        for (const line of order.getOrderlines()) {
            const discount = Math.max(0, Number(line.dolan_discount_base_percent || 0));
            if (!discount || Number(line.qty || 0) <= 0) continue;
            if (!line.dolan_discount_reason) {
                const reason = await makeAwaitable(this.dialog, TextInputPopup, {
                    title: `Motivo del descuento · ${line.product_id.display_name || line.product_id.name}`,
                    rows: 3,
                    startingValue: "",
                });
                if (typeof reason !== "string" || !reason.trim()) {
                    this.notification.add("Ingresá el motivo para continuar con el descuento.", { type: "warning" });
                    return false;
                }
                line.dolan_discount_reason = reason.trim().slice(0, 256);
            }
            const approval = await this.data.call(
                "dolan.discount.approval",
                "action_prepare_pos_discount",
                [this.session.id, order.uuid, line.uuid, line.product_id.id, discount,
                    line.dolan_discount_reason, line.dolan_discount_approval_uuid || false]
            );
            if (approval.status !== "authorized") {
                line.dolan_discount_approval_uuid = approval.request_uuid;
                this.notification.add(
                    "Se envió la solicitud al supervisor. Cuando la apruebe, presioná Cobrar nuevamente.",
                    { type: "warning", sticky: true }
                );
                return false;
            }
            line.dolan_discount_approval_uuid = approval.request_uuid || false;
        }
        const employeeLines = order.getOrderlines().filter((line) => line.dolan_discount_employee_token);
        const employeeTokens = [...new Set(employeeLines.map((line) => line.dolan_discount_employee_token))];
        if (employeeTokens.length > 1) {
            this.notification.add("La orden tiene más de un beneficio de empleado. Quitá uno antes de cobrar.", { type: "danger", sticky: true });
            return false;
        }
        if (employeeTokens.length) {
            const token = employeeTokens[0];
            const lineData = employeeLines.map((line) => ({
                uuid: line.uuid, product_id: line.product_id.id, qty: line.qty,
                unit_price: line.price_unit, current_discount: 0,
            }));
            let result;
            try {
                result = await this.data.call("dolan.discount.employee.claim", "action_validate_pos_claim", [
                    this.session.id, order.uuid, token, lineData,
                ]);
            } catch (error) {
                this.notification.add(error.message || "No se pudo validar el beneficio de empleado.", { type: "danger", sticky: true });
                return false;
            }
            const byUuid = new Map((result.proposals || []).map((item) => [item.line_uuid, item]));
            for (const line of employeeLines) {
                const proposal = byUuid.get(line.uuid);
                if (!proposal) {
                    this.notification.add("El beneficio ya no aplica a una línea de la orden. Revisá el carrito.", { type: "warning", sticky: true });
                    return false;
                }
                const base = Math.max(0, Number(line.qty || 0) * Number(line.price_unit || 0));
                const percent = base ? Math.min(100, Number(proposal.discount_amount || 0) * 100 / base) : 0;
                line.dolan_discount_employee_percent = percent;
                line.dolan_discount_employee_applications = [proposal];
                line._dolanCampaignUpdate = true;
                line.setDiscount(percent);
                line._dolanCampaignUpdate = false;
            }
        }
        const allLines = order.getOrderlines();
        let promoLines = paymentMethodId
            ? allLines.filter((line) => !Number(line.dolan_discount_base_percent || 0) && !line.dolan_discount_employee_token)
            : allLines.filter((line) => line.dolan_discount_applications?.length && !Number(line.dolan_discount_base_percent || 0));
        if (paymentMethodId) {
            order._dolanPaymentMethodId = Number(paymentMethodId);
            if (allLines.some((line) => Number(line.dolan_discount_base_percent || 0) || line.dolan_discount_employee_token)) {
                this.notification.add("Quitá los descuentos manuales o el beneficio de empleado antes de aplicar una promoción por medio de pago.", { type: "warning", sticky: true });
                return false;
            }
            for (const line of promoLines) {
                line.dolan_discount_applications = proposalForLine(line, new Date(), paymentMethodId);
            }
        }
        if (!promoLines.length) return true;
        const lines = promoLines.map((line) => ({
            uuid: line.uuid,
            product_id: line.product_id.id,
            qty: line.qty,
            unit_price: line.price_unit,
        }));
        let result;
        const previousApplications = new Map(promoLines.map((line) => [line.uuid, line.dolan_discount_applications || []]));
        try {
            result = await this.data.call(
                "dolan.discount.reservation",
                "action_prepare_pos_order",
                [this.session.id, order.uuid, lines, order.partner_id?.id || false, paymentMethodId || false]
            );
        } catch (error) {
            for (const line of promoLines) line.dolan_discount_applications = previousApplications.get(line.uuid) || [];
            this.notification.add(
                `No se pudo confirmar la autorización de descuentos con el servidor. La orden queda sin cambios y el cobro está bloqueado hasta reconectar. ${error.message || ""}`,
                { type: "danger", sticky: true }
            );
            return false;
        }
        if (result.status !== "ready") {
            for (const line of promoLines) {
                line.dolan_discount_applications = previousApplications.get(line.uuid) || [];
                const baseDiscount = Math.max(0, Number(line.dolan_discount_base_percent || 0));
                line._dolanCampaignUpdate = true;
                const previous = line.dolan_discount_applications.reduce((sum, item) => sum + Number(item.discount_amount || 0), 0);
                const base = Math.max(0, Number(line.qty || 0) * Number(line.price_unit || 0));
                line.setDiscount(baseDiscount || !base ? baseDiscount : Math.min(100, previous * 100 / base));
                line._dolanCampaignUpdate = false;
            }
            this.notification.add(result.message || "No se pudo autorizar la promoción. Revisá el total.", {
                type: "warning", sticky: true,
            });
            return false;
        }
        const byUuid = new Map();
        for (const item of result.proposals || []) {
            if (!byUuid.has(item.line_uuid)) byUuid.set(item.line_uuid, []);
            byUuid.get(item.line_uuid).push(item);
        }
        for (const line of promoLines) {
            const applications = byUuid.get(line.uuid) || [];
            const base = Math.max(0, Number(line.qty || 0) * Number(line.price_unit || 0));
            const amount = applications.reduce((sum, item) => sum + Number(item.discount_amount || 0), 0);
            const percent = base ? Math.min(100, amount * 100 / base) : 0;
            line.dolan_discount_applications = applications;
            line._dolanCampaignUpdate = true;
            line.setDiscount(percent);
            line._dolanCampaignUpdate = false;
        }
        return true;
    },

    async pay() {
        if (!await this.authorizeDolanPromotions(this.getOrder())) return;
        return super.pay(...arguments);
    },

    async setup() {
        await super.setup(...arguments);
        window.addEventListener("offline", () => {
            const order = this.getOrder();
            const hasServerBenefits = order?.getOrderlines?.().some((line) =>
                line.dolan_discount_applications?.length ||
                Number(line.dolan_discount_base_percent || 0) ||
                line.dolan_discount_employee_token
            );
            if (hasServerBenefits) {
                this.notification.add(
                    "Se cortó la conexión con la caja. El total autorizado queda visible, pero no se puede confirmar la venta hasta reconectar. No repitas un cobro que la terminal ya haya aceptado.",
                    { type: "danger", sticky: true }
                );
            }
        });
        const recalculate = (order) => {
            if (!order || order.state !== "draft" || order._dolanCampaignRecomputing) return;
            order._dolanCampaignRecomputing = true;
            try {
                for (const line of order.getOrderlines()) {
                    const baseDiscount = Math.max(0, Math.min(100, Number(line.dolan_discount_base_percent || 0)));
                    // Keep this first POS slice separate from Odoo's native/manual
                    // discount control. A cashier changing the discount replaces
                    // the campaign preview instead of stacking hidden percentages.
                    if (line.dolan_discount_employee_token) {
                        line.dolan_discount_applications = [];
                        line._dolanCampaignUpdate = true;
                        line.setDiscount(Number(line.dolan_discount_employee_percent || 0));
                        line._dolanCampaignUpdate = false;
                        continue;
                    }
                    const applications = baseDiscount ? [] : proposalForLine(line, new Date(), order._dolanPaymentMethodId || false);
                    const base = Math.max(0, Number(line.qty || 0) * Number(line.price_unit || 0));
                    const promoAmount = applications.reduce((sum, item) => sum + item.discount_amount, 0);
                    const promoPercent = base ? Math.min(100, promoAmount * 100 / base) : 0;
                    const combinedDiscount = 100 * (1 - (1 - baseDiscount / 100) * (1 - promoPercent / 100));
                    line.dolan_discount_base_percent = baseDiscount;
                    line.dolan_discount_applications = applications;
                    line._dolanCampaignUpdate = true;
                    line.setDiscount(combinedDiscount);
                    line._dolanCampaignUpdate = false;
                }
            } finally {
                order._dolanCampaignRecomputing = false;
            }
        };
        const lineModel = this.models["pos.order.line"];
        lineModel.addEventListener("create", ({ ids }) => {
            for (const id of ids || []) recalculate(lineModel.get(id)?.order_id);
        });
        lineModel.addEventListener("update", ({ id }) => recalculate(lineModel.get(id)?.order_id));
    },
});

patch(ProductScreen.prototype, {
    async fastValidate(paymentMethod) {
        if (!await this.pos.authorizeDolanPromotions(this.pos.getOrder())) return;
        return super.fastValidate(...arguments);
    },
});

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod, args = {}) {
        const order = this.currentOrder;
        const methodId = paymentMethod?.id;
        const existingLines = order?.payment_ids || [];
        const currentPaymentPromotion = order?.getOrderlines?.().some((line) =>
            (line.dolan_discount_applications || []).some((item) => item.rule_snapshot?.payment_method_id)
        );
        const selectedMethodPromotion = methodId && order?.getOrderlines?.().some((line) =>
            proposalForLine(line, new Date(), methodId).some((item) => item.rule_snapshot?.payment_method_id)
        );
        const hasDifferentTender = existingLines.some((line) => line.payment_method_id?.id !== methodId);
        if ((currentPaymentPromotion || selectedMethodPromotion) && hasDifferentTender) {
            this.notification.add("Esta promoción exige un único medio de pago. Quitá el pago anterior antes de elegir otro.", { type: "warning", sticky: true });
            return;
        }
        if (order && methodId) order._dolanPaymentMethodId = Number(methodId);
        if (methodId && !await this.pos.authorizeDolanPromotions(order, methodId)) return;
        return super.addNewPaymentLine(...arguments);
    },

    async onClickValidate(args = {}) {
        const order = this.currentOrder;
        const hasServerBenefits = order?.getOrderlines?.().some((line) =>
            line.dolan_discount_applications?.length ||
            Number(line.dolan_discount_base_percent || 0) ||
            line.dolan_discount_employee_token
        );
        if (hasServerBenefits && !navigator.onLine) {
            this.notification.add(
                "No se puede confirmar una venta con descuentos autorizados mientras la caja está sin conexión. Esperá a recuperar la red y verificá el estado de cualquier cobro iniciado.",
                { type: "danger", sticky: true }
            );
            return;
        }
        return super.onClickValidate(...arguments);
    },
});

patch(ControlButtons.prototype, {
    async clickDolanEmployeeBenefit() {
        const order = this.pos.getOrder();
        if (!order || order.state !== "draft" || order.isEmpty()) {
            this.notification.add("Cargá productos antes de aplicar el beneficio.", { type: "warning" });
            return;
        }
        const dni = await makeAwaitable(this.dialog, TextInputPopup, {
            title: "Beneficio de empleado",
            rows: 1,
            startingValue: "",
        });
        if (dni === undefined || dni === null) return;
        const existingToken = order.getOrderlines().find((line) => line.dolan_discount_employee_token)?.dolan_discount_employee_token;
        if (!dni.trim()) {
            if (existingToken) {
                await this.pos.data.call("dolan.discount.employee.claim", "action_release_pos_claim", [
                    this.pos.session.id, order.uuid, existingToken,
                ]);
            }
            for (const line of order.getOrderlines()) {
                if (!line.dolan_discount_employee_token) continue;
                line.dolan_discount_employee_token = false;
                line.dolan_discount_employee_applications = [];
                line.dolan_discount_employee_percent = 0;
                line._dolanCampaignUpdate = true;
                line.setDiscount(Number(line.dolan_discount_base_percent || 0));
                line._dolanCampaignUpdate = false;
            }
            this.notification.add("Se quitó el beneficio de empleado.", { type: "info" });
            return;
        }
        const lineData = order.getOrderlines().filter((line) => Number(line.qty || 0) > 0).map((line) => ({
            uuid: line.uuid, product_id: line.product_id.id, qty: line.qty,
            unit_price: line.price_unit,
            current_discount: line.dolan_discount_employee_token ? 0 : Number(line.discount || 0),
        }));
        try {
            const result = await this.pos.data.call("dolan.discount.employee.benefit", "action_apply_dni_pos", [
                this.pos.session.id, order.uuid, lineData, dni.trim(),
            ]);
            if (result.status !== "ready") {
                if (result.status === "pending_approval") {
                    for (const line of order.getOrderlines()) {
                        if (!line.dolan_discount_employee_token) continue;
                        line.dolan_discount_employee_token = false;
                        line.dolan_discount_employee_applications = [];
                        line.dolan_discount_employee_percent = 0;
                        line._dolanCampaignUpdate = true;
                        line.setDiscount(Number(line.dolan_discount_base_percent || 0));
                        line._dolanCampaignUpdate = false;
                    }
                }
                this.notification.add(result.message || "No se pudo aplicar el beneficio de empleado.", { type: "warning", sticky: true });
                return;
            }
            for (const line of order.getOrderlines()) {
                line.dolan_discount_employee_token = false;
                line.dolan_discount_employee_applications = [];
                line.dolan_discount_employee_percent = 0;
            }
            const byUuid = new Map((result.proposals || []).map((item) => [item.line_uuid, item]));
            for (const line of order.getOrderlines()) {
                const proposal = byUuid.get(line.uuid);
                if (!proposal) continue;
                const base = Math.max(0, Number(line.qty || 0) * Number(line.price_unit || 0));
                line.dolan_discount_employee_token = result.token;
                line.dolan_discount_employee_applications = [proposal];
                line.dolan_discount_employee_percent = base ? Number(proposal.discount_amount || 0) * 100 / base : 0;
                line.dolan_discount_applications = [];
                line._dolanCampaignUpdate = true;
                line.setDiscount(line.dolan_discount_employee_percent);
                line._dolanCampaignUpdate = false;
            }
            this.notification.add(`Beneficio aplicado: ${result.benefit_name}.`, { type: "success" });
        } catch (error) {
            this.notification.add(error.message || "No se pudo validar el DNI del empleado.", { type: "danger", sticky: true });
        }
    },
});
