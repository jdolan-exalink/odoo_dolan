/**
 * After a successful POS close, Odoo calls the daily sales receipt with
 * `download: true`; the native fallback downloads a PNG. Prefer the receipt
 * printers configured on this POS and use Odoo's native PDF report otherwise.
 */
import { patch } from "@web/core/utils/patch";
import { PosTicketPrinterPlugin } from "@point_of_sale/app/plugins/pos_ticket_printer_plugin";

patch(PosTicketPrinterPlugin.prototype, {
    async printSaleDetailsReceipt({ download = false } = {}) {
        if (!download) {
            return super.printSaleDetailsReceipt(...arguments);
        }

        if (this.hasReceiptPrinters) {
            const generator = this.getGenerator({ models: this.data.models });
            const saleDetails = await this.data.call(
                "report.point_of_sale.report_saledetails",
                "get_sale_details",
                [false, false, false, [this.session.id]]
            );
            const data = generator.generateSaleDetailsData(saleDetails);
            const iframe = await this.generateIframe("point_of_sale.pos_sale_details_receipt", data);
            const printers = [
                this.defaultPrinter,
                ...this.receiptPrinters.filter((printer) => printer.id !== this.defaultPrinter?.id),
            ].filter((printer) => printer?._instance?.print);

            for (const printer of printers) {
                try {
                    const result = await this.print({ printer, iframe });
                    if (result?.successful) {
                        return result;
                    }
                } catch (error) {
                    console.warn(`No se pudo imprimir el cierre en ${printer.name}:`, error);
                }
            }

            this.notification.add(
                "No se pudo confirmar la impresión del cierre. Se abrirá el informe en PDF.",
                { type: "warning", sticky: true }
            );
        }

        const report = this.env.services.report;
        if (!report?.doAction) {
            throw new Error("No está disponible el servicio para descargar el cierre en PDF.");
        }
        return report.doAction("point_of_sale.sale_details_report", [this.session.id]);
    },
});
