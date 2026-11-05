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
