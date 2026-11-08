import csv
import io

from odoo.exceptions import UserError


class ScaleExporter:
    """Contract for deterministic manufacturer/file-format serializers."""

    adapter_code = None
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.adapter_code:
            ScaleExporter._registry[cls.adapter_code] = cls

    @classmethod
    def get(cls, adapter_code):
        exporter = cls._registry.get(adapter_code)
        return exporter() if exporter else None

    def serialize(self, records, profile):
        raise NotImplementedError


class KretzITegraExporter(ScaleExporter):
    adapter_code = 'kretz_itegra'

    def serialize(self, records, profile):
        raise UserError(
            'Kretz/iTegra está bloqueado hasta analizar un archivo real aceptado por iTegra '
            'y verificar su importación en la versión objetivo.'
        )


class GenericCSVExporter(ScaleExporter):
    """DOLAN interchange CSV; does not claim a vendor-specific device dialect."""

    adapter_code = 'generic_csv_v1'

    def serialize(self, records, profile):
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=';', lineterminator='\r\n', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['PLU', 'Código de barras', 'Descripción', 'Precio', 'Moneda'])
        decimals = max(0, min(int(profile.price_decimals or 2), 6))
        for record in records:
            price = record.get('price')
            if price is None:
                raise UserError('No se puede exportar un precio vacío.')
            writer.writerow([
                record.get('plu') or '', record.get('barcode') or '',
                record.get('product') or '', f'{float(price):.{decimals}f}',
                record.get('currency') or '',
            ])
        return 'DOLAN_BALANZA_GENERIC_CSV_V1.csv', output.getvalue().encode('utf-8-sig')
