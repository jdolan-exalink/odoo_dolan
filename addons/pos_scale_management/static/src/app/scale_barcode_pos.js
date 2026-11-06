import { onWillDestroy } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

function ean13Valid(code) {
    if (!/^\d{13}$/.test(code)) return false;
    const sum = [...code.slice(0, 12)].reduce(
        (total, digit, index) => total + Number(digit) * (index % 2 ? 3 : 1),
        0
    );
    return String((10 - (sum % 10)) % 10) === code[12];
}

function parseScaleBarcode(code, profiles) {
    for (const profile of profiles || []) {
        if (code.length !== Number(profile.barcode_length) || !/^\d+$/.test(code)) continue;
        if (profile.prefix && !code.startsWith(profile.prefix)) continue;
        if (profile.check_digit && !ean13Valid(code)) return { invalid: true };
        const startProduct = Number(profile.product_start) - 1;
        const startValue = Number(profile.value_start) - 1;
        const plu = code.slice(startProduct, startProduct + Number(profile.product_length));
        const encoded = code.slice(startValue, startValue + Number(profile.value_length));
        if (plu.length !== Number(profile.product_length) || encoded.length !== Number(profile.value_length)) {
            return { invalid: true };
        }
        const value = Number(encoded) / (10 ** Number(profile.decimals));
        if (!Number.isFinite(value) || value <= 0) return { invalid: true };
        const productId = profile.products?.[plu];
        if (!productId) return { profile, plu, invalid: true };
        return { profile, productId, plu, value, value_type: profile.value_type, code };
    }
    return false;
}

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        const barcodeReader = this.barcodeReader;
        const originalScan = barcodeReader?.scan?.bind(barcodeReader);
        const profiles = this.pos.config.scale_barcode_profiles || [];
        if (originalScan && profiles.length) {
            barcodeReader.scan = async (code) => {
                const parsed = parseScaleBarcode(String(code || "").trim(), profiles);
                if (!parsed) return originalScan(code);
                return barcodeReader.mutex.exec(async () => {
                    if (parsed.invalid) {
                        this.notification.add("La etiqueta de balanza no es válida o el PLU no está asignado a esta sucursal.", { type: "warning" });
                        this.sound.play("scan-error");
                        return;
                    }
                    await this._barcodeScaleProductAction(parsed);
                });
            };
            onWillDestroy(() => {
                barcodeReader.scan = originalScan;
            });
        }
    },

    async _barcodeScaleProductAction(code) {
        const product = this.pos.models["product.product"].get(code.productId);
        if (!product || !(await this.pos.canAddProductToCurrentOrder(product.product_tmpl_id))) {
            this.sound.play("scan-error");
            return;
        }
        const allocation = this.pos.autoCourseAllocation(product);
        const line = await this.pos.addLineToCurrentOrder(
            { product_id: product, product_tmpl_id: product.product_tmpl_id },
            { code: { code: code.code, scale_plu: code.plu } },
            product.needToConfigure()
        );
        if (!line) return;
        if (code.value_type === "weight") {
            line.setQuantity(code.value);
        } else {
            line.setQuantity(1);
            line.setUnitPrice(code.value);
        }
        this.pos.cleanAutoCourseAllocation(line, allocation);
        this.sound.play("beep");
        this.numberBuffer.reset();
    },
});
