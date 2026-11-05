import json
import hashlib
import io
import logging
import re
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes

from ..services.exporter_registry import ScaleExporter

_logger = logging.getLogger(__name__)


class ScaleExportJob(models.Model):
    _name = 'scale.export.job'
    _description = 'Historial de exportaciones de balanzas'
    _order = 'create_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default='Nueva exportación', copy=False, index=True)
    job_type = fields.Selection([('single', 'Balanza individual'), ('branch_zip', 'Sucursal (ZIP)')], default='single', required=True)
    device_id = fields.Many2one('scale.device', check_company=True, ondelete='restrict', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    profile_id = fields.Many2one('scale.export.profile', ondelete='restrict')
    state = fields.Selection([
        ('draft', 'Borrador'), ('validated', 'Validado'), ('generated', 'Generado'),
        ('downloaded', 'Descargado'), ('blocked', 'Bloqueado'), ('failed', 'Error'),
        ('pending_import', 'Pendiente de importación'), ('imported_reported', 'Importado informado'),
        ('import_failed_reported', 'Importación con error informada'),
    ], default='draft', required=True, index=True)
    generated_at = fields.Datetime(readonly=True, copy=False)
    imported_reported_at = fields.Datetime(readonly=True, copy=False)
    imported_reported_by = fields.Many2one('res.users', readonly=True, copy=False)
    file_data = fields.Binary(attachment=True, readonly=True, copy=False)
    file_name = fields.Char(readonly=True, copy=False)
    checksum_sha256 = fields.Char(readonly=True, copy=False)
    record_count = fields.Integer(readonly=True, copy=False)
    snapshot_json = fields.Text(readonly=True, copy=False)
    error_report = fields.Text(readonly=True, copy=False)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        raise UserError(_('El historial solo se crea desde la acción de previsualización de una balanza.'))

    @api.model
    def _safe_name(self, *parts):
        values = [re.sub(r'[^A-Za-z0-9_-]+', '_', str(part or '')).strip('_') for part in parts]
        return '_'.join(value for value in values if value)[:180] or 'BALANZA'

    @api.model
    def _snapshot_for_device(self, device):
        products, prices, errors = device._resolve_export_preview()
        rows = []
        for product in products:
            result = prices.get(product.id, {})
            rows.append({
                'product_id': product.id,
                'product': product.display_name,
                'barcode': product.barcode or '',
                'plu': result.get('plu') or '',
                'quantity_uom': product.uom_id.name,
                'price': result.get('price'),
                'currency': result.get('currency') or '',
                'price_source': result.get('source') or '',
                'tax_excluded': result.get('tax_excluded'),
                'tax_included': result.get('tax_included'),
                'tax_amount': result.get('tax_amount'),
            })
        return rows, errors

    @api.model
    def create_preview(self, device):
        if not any(self.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
            'pos_scale_management.group_scale_operator',
        )):
            raise UserError(_('No tenés permiso para previsualizar exportaciones de balanzas.'))
        if isinstance(device, int):
            device = self.env['scale.device'].browse(device)
        device.ensure_one()
        device.check_access('read')
        rows, errors = self._snapshot_for_device(device)
        profile = device.profile_id
        if profile.validation_state != 'validated':
            errors.append(_('El perfil %s no está validado con una importación real en iTegra. No se generará un archivo de producción.') % profile.display_name)
        if not ScaleExporter.get(profile.adapter_code):
            errors.append(_('No existe un adaptador registrado para el perfil %s.') % profile.display_name)
        snapshot = {
            'generated_for_preview_at': fields.Datetime.to_string(fields.Datetime.now()),
            'company': device.company_id.display_name,
            'warehouse': device.warehouse_id.display_name,
            'device': device.display_name,
            'profile': profile.display_name,
            'profile_state': profile.validation_state,
            'rows': rows,
            'warnings': errors,
        }
        date_stamp = fields.Date.context_today(self).strftime('%Y%m%d')
        name = self._safe_name(device.company_id.name, device.warehouse_id.code, device.code, date_stamp)
        vals = {
            'name': name,
            'device_id': device.id,
            'warehouse_id': device.warehouse_id.id,
            'company_id': device.company_id.id,
            'profile_id': profile.id,
            'state': 'blocked' if errors else 'validated',
            'record_count': len(rows),
            'snapshot_json': json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2),
            'error_report': '\n'.join(errors) or False,
        }
        # Do not use a context flag for this internal capability: callers can supply
        # arbitrary RPC contexts. Bypass only this model's public create guard.
        return super(ScaleExportJob, self.sudo()).create([vals])

    @api.model
    def create_export(self, device):
        if not any(self.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
        )):
            raise UserError(_('Solo un administrador o responsable de sucursal puede solicitar una exportación.'))
        if isinstance(device, int):
            device = self.env['scale.device'].browse(device)
        device.ensure_one()
        device.check_access('read')
        job = self.create_preview(device)
        exporter = ScaleExporter.get(device.profile_id.adapter_code)
        if job.error_report or not exporter:
            return job
        # The serializer is called only for profiles that passed all validation rules.
        # A job can be marked generated only after bytes and a hash are actually produced.
        snapshot = json.loads(job.snapshot_json or '{}')
        try:
            file_name, file_bytes = exporter.serialize(snapshot.get('rows', []), device.profile_id)
        except UserError as exc:
            super(ScaleExportJob, job.sudo()).write({'state': 'failed', 'error_report': str(exc)})
            return job
        except Exception:
            _logger.exception('Unexpected balanza export failure for job %s', job.id)
            super(ScaleExportJob, job.sudo()).write({
                'state': 'failed',
                'error_report': _('El adaptador falló durante la generación. Revisá el registro técnico del servidor.'),
            })
            return job
        import base64
        digest = hashlib.sha256(file_bytes).hexdigest()
        # Create-once immutable history: file fields are populated at creation time in a
        # dedicated follow-up path once a real adapter is enabled.
        super(ScaleExportJob, job.sudo()).write({
            'state': 'generated', 'file_name': file_name,
            'file_data': BinaryBytes(file_bytes, filename=file_name), 'checksum_sha256': digest,
            'generated_at': fields.Datetime.now(),
        })
        return job

    @api.model
    def create_branch_export(self, warehouse):
        if isinstance(warehouse, int):
            warehouse = self.env['stock.warehouse'].browse(warehouse)
        warehouse.ensure_one()
        is_admin = self.env.user.has_group('pos_scale_management.group_scale_admin')
        is_manager = self.env.user.has_group('pos_scale_management.group_scale_branch_manager')
        if not (is_admin or is_manager):
            raise UserError(_('Solo un administrador o responsable de sucursal puede exportar por sucursal.'))
        if not is_admin and warehouse not in self.env.user.scale_allowed_warehouse_ids:
            raise UserError(_('No tenés autorizada esta sucursal.'))
        if warehouse.company_id not in self.env.companies:
            raise UserError(_('La empresa de la sucursal no está activa para tu usuario.'))
        devices = self.env['scale.device'].search([
            ('warehouse_id', '=', warehouse.id), ('active', '=', True),
        ], order='code, id')
        if not devices:
            raise UserError(_('Esta sucursal no tiene balanzas activas configuradas.'))

        date_stamp = fields.Date.context_today(self).strftime('%Y%m%d')
        job_name = self._safe_name(warehouse.company_id.name, warehouse.code, 'BALANZAS', date_stamp)
        entries, errors, prepared = [], [], []
        for device in devices:
            products, prices, validation_errors = device._resolve_export_preview()
            if device.profile_id.validation_state != 'validated':
                validation_errors.append(_('El perfil no está validado con una prueba real.'))
            exporter = ScaleExporter.get(device.profile_id.adapter_code)
            if not exporter:
                validation_errors.append(_('No hay un adaptador registrado para este perfil.'))
            item = {
                'device': device.display_name,
                'device_code': device.code,
                'profile': device.profile_id.display_name,
                'record_count': len(products),
                'rows': [{
                    'product_id': product.id,
                    'product': product.display_name,
                    'barcode': product.barcode or '',
                    'plu': prices.get(product.id, {}).get('plu') or '',
                    'quantity_uom': product.uom_id.name,
                    'price': prices.get(product.id, {}).get('price'),
                    'currency': prices.get(product.id, {}).get('currency') or '',
                    'price_source': prices.get(product.id, {}).get('source') or '',
                    'tax_excluded': prices.get(product.id, {}).get('tax_excluded'),
                    'tax_included': prices.get(product.id, {}).get('tax_included'),
                    'tax_amount': prices.get(product.id, {}).get('tax_amount'),
                } for product in products],
                'validation_errors': list(dict.fromkeys(validation_errors)),
            }
            entries.append(item)
            errors.extend(f"{device.display_name}: {message}" for message in item['validation_errors'])
            if not validation_errors:
                prepared.append((device, exporter, item))

        snapshot = {
            'created_at': fields.Datetime.to_string(fields.Datetime.now()),
            'company': warehouse.company_id.display_name,
            'warehouse': warehouse.display_name,
            'devices': entries,
            'policy': 'abort_all_if_any_device_fails',
        }
        vals = {
            'name': job_name, 'job_type': 'branch_zip',
            'warehouse_id': warehouse.id, 'company_id': warehouse.company_id.id,
            'state': 'blocked' if errors else 'validated',
            'record_count': sum(item['record_count'] for item in entries),
            'snapshot_json': json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2),
            'error_report': '\n'.join(errors) or False,
        }
        job = super(ScaleExportJob, self.sudo()).create([vals])
        if errors:
            return job

        zip_buffer = io.BytesIO()
        manifest = {
            'company': warehouse.company_id.display_name,
            'warehouse': warehouse.display_name,
            'generated_at': snapshot['created_at'],
            'files': [],
        }
        try:
            with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for device, exporter, item in prepared:
                    file_name, file_bytes = exporter.serialize(item['rows'], device.profile_id)
                    safe_file_name = self._safe_name(device.code, file_name.rsplit('.', 1)[0])
                    extension = file_name.rsplit('.', 1)[-1] if '.' in file_name else 'dat'
                    file_name = f'{safe_file_name}.{re.sub(r"[^A-Za-z0-9]+", "", extension) or "dat"}'
                    archive.writestr(file_name, file_bytes)
                    manifest['files'].append({
                        'file': file_name, 'device_code': device.code,
                        'device': device.display_name, 'profile': device.profile_id.display_name,
                        'record_count': item['record_count'],
                        'sha256': hashlib.sha256(file_bytes).hexdigest(),
                    })
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        except UserError as exc:
            super(ScaleExportJob, job.sudo()).write({'state': 'failed', 'error_report': str(exc)})
            return job
        except Exception:
            _logger.exception('Unexpected branch scale export failure for job %s', job.id)
            super(ScaleExportJob, job.sudo()).write({
                'state': 'failed',
                'error_report': _('El adaptador falló durante el lote. Revisá el registro técnico del servidor.'),
            })
            return job

        file_bytes = zip_buffer.getvalue()
        file_name = f'{self._safe_name(warehouse.company_id.name, warehouse.code, date_stamp)}.zip'
        super(ScaleExportJob, job.sudo()).write({
            'state': 'generated', 'file_name': file_name,
            'file_data': BinaryBytes(file_bytes, filename=file_name),
            'checksum_sha256': hashlib.sha256(file_bytes).hexdigest(),
            'generated_at': fields.Datetime.now(),
        })
        return job

    def action_download(self):
        self.ensure_one()
        self.check_access('read')
        if not any(self.env.user.has_group(group) for group in (
            'pos_scale_management.group_scale_admin',
            'pos_scale_management.group_scale_branch_manager',
            'pos_scale_management.group_scale_operator',
        )):
            raise UserError(_('No tenés permiso para descargar exportaciones de balanzas.'))
        if not self.file_data or self.state not in ('generated', 'downloaded', 'pending_import', 'imported_reported', 'import_failed_reported'):
            raise UserError(_('Esta exportación no contiene un archivo descargable.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/pos_scale_management/export/{self.id}/download',
            'target': 'self',
        }

    def _mark_downloaded(self):
        self.ensure_one()
        self.check_access('read')
        if self.state == 'generated':
            super(ScaleExportJob, self.sudo()).write({'state': 'downloaded'})

    def action_report_import_result(self, imported=True, note=''):
        self.ensure_one()
        imported = self.env.context.get('imported', imported)
        if not self.env.user.has_group('pos_scale_management.group_scale_branch_manager') and not self.env.user.has_group('pos_scale_management.group_scale_admin'):
            raise UserError(_('Solo un responsable autorizado puede informar el resultado de importación.'))
        if self.state not in ('generated', 'downloaded', 'pending_import', 'imported_reported', 'import_failed_reported'):
            raise UserError(_('Solo se puede informar la importación de un archivo generado.'))
        self.check_access('write')
        super(ScaleExportJob, self.sudo()).write({
            'state': 'imported_reported' if imported else 'import_failed_reported',
            'imported_reported_at': fields.Datetime.now(),
            'imported_reported_by': self.env.user.id,
            'notes': note or self.notes,
        })

    def write(self, vals):
        protected = {
            'device_id', 'warehouse_id', 'company_id', 'profile_id', 'record_count',
            'snapshot_json', 'error_report', 'create_date', 'create_uid',
            'state', 'generated_at', 'imported_reported_at', 'imported_reported_by',
            'file_data', 'file_name', 'checksum_sha256',
        }
        if protected.intersection(vals):
            raise UserError(_('Los datos de auditoría solo cambian mediante acciones internas autorizadas.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('El historial de exportaciones es inmutable y no se puede borrar.'))
