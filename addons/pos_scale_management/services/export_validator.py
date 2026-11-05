from odoo import _


class ExportValidator:
    """Validate a preview before a compatible output adapter is allowed to run."""

    def __init__(self, device):
        self.device = device

    def validate(self, products, prices):
        device = self.device
        errors = []
        profile = device.profile_id
        if not products:
            errors.append(_('La balanza no tiene productos asignados.'))

        seen_plu = {}
        for product in products:
            row = prices.get(product.id, {})
            plu = row.get('plu') or ''
            if profile.requires_plu and not plu:
                errors.append(_('Falta PLU para %s.') % product.display_name)
            if plu:
                if plu in seen_plu:
                    errors.append(_('PLU duplicado %s: %s y %s.') % (plu, seen_plu[plu], product.display_name))
                else:
                    seen_plu[plu] = product.display_name
                if profile.max_plu_length and len(plu) > profile.max_plu_length:
                    errors.append(_('El PLU %s de %s excede el máximo de %s caracteres.') % (plu, product.display_name, profile.max_plu_length))
            if row.get('price') is None or row.get('price') < 0:
                errors.append(_('El precio de %s no es válido.') % product.display_name)
            if not row.get('currency'):
                errors.append(_('No se pudo resolver la moneda de %s.') % product.display_name)

        if profile.validation_state != 'validated':
            errors.append(_('El perfil de formato está %s; no se puede generar un archivo productivo.') % dict(profile._fields['validation_state'].selection).get(profile.validation_state))
        # Kretz/iTegra remains intentionally blocked until a real accepted file and import test exist.
        if profile.adapter_code == 'kretz_itegra':
            errors.append(_('Adaptador Kretz/iTegra pendiente de validar con archivos reales.'))
        return list(dict.fromkeys(errors))
