# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, datetime, timedelta
import json
import logging
import urllib.parse
import urllib.request

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class DolanViewPlannerItem(models.Model):
    _name = 'dolan.view.planner.item'
    _description = 'DOLAN Multi-View Planner Item (Gantt / Cohort / Grid / Map)'
    _order = 'date_start asc, sequence asc, id desc'

    name = fields.Char(string='Título / Tarea', required=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    category_type = fields.Selection(
        selection=[
            ('project', 'Proyecto / Tarea'),
            ('mrp', 'Orden de Producción'),
            ('rental', 'Alquiler / Reserva'),
            ('hr', 'Asignación RRHH / Turno'),
            ('contact', 'Visita / Contacto Geolocalizado'),
        ],
        string='Ámbito Operativo',
        default='project',
        required=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsable',
        default=lambda self: self.env.user,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente / Contacto',
    )
    date_start = fields.Datetime(
        string='Fecha de Inicio',
        required=True,
        default=fields.Datetime.now,
    )
    date_stop = fields.Datetime(
        string='Fecha de Fin',
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=3),
    )
    date_cohort_close = fields.Date(
        string='Fecha de Retención / Cierre (Cohort)',
        help='Fecha en la que el registro permanece activo o finaliza su ciclo para análisis de retención.',
    )
    duration_hours = fields.Float(
        string='Horas Planificadas',
        compute='_compute_duration_hours',
        store=True,
        readonly=False,
    )
    worked_hours = fields.Float(
        string='Horas Imputadas (Grid)',
        default=8.0,
    )
    progress = fields.Float(
        string='Progreso (%)',
        default=0.0,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Planificado'),
            ('in_progress', 'En Curso'),
            ('done', 'Completado'),
            ('blocked', 'Bloqueado'),
        ],
        string='Estado',
        default='draft',
        required=True,
    )
    color = fields.Integer(string='Índice de Color', default=4)
    dependency_ids = fields.Many2many(
        'dolan.view.planner.item',
        'dolan_planner_dependency_rel',
        'item_id',
        'depends_on_id',
        string='Predecesoras (Gantt)',
    )
    latitude = fields.Float(string='Latitud', digits=(10, 7))
    longitude = fields.Float(string='Longitud', digits=(10, 7))
    street_address = fields.Char(string='Dirección (OpenStreetMap)')
    notes = fields.Text(string='Notas')

    @api.depends('date_start', 'date_stop')
    def _compute_duration_hours(self):
        for rec in self:
            if rec.date_start and rec.date_stop and rec.date_stop >= rec.date_start:
                delta = rec.date_stop - rec.date_start
                rec.duration_hours = round(delta.total_seconds() / 3600.0, 2)
            else:
                rec.duration_hours = 0.0

    @api.constrains('date_start', 'date_stop')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_stop and rec.date_stop < rec.date_start:
                raise ValidationError(_('La fecha de fin no puede ser anterior a la fecha de inicio.'))

    @api.constrains('progress')
    def _check_progress(self):
        for rec in self:
            if rec.progress < 0.0 or rec.progress > 100.0:
                raise ValidationError(_('El porcentaje de progreso debe estar entre 0 y 100.'))

    def action_geocode_nominatim(self):
        """Geocode using free OpenStreetMap Nominatim API without proprietary keys."""
        for rec in self:
            address = rec.street_address
            if not address and rec.partner_id:
                parts = [
                    rec.partner_id.street or '',
                    rec.partner_id.city or '',
                    rec.partner_id.country_id.name or '',
                ]
                address = ', '.join(p for p in parts if p)
            if not address:
                raise UserError(_('Ingrese una dirección o seleccione un contacto con dirección para geolocalizar.'))
            query = urllib.parse.urlencode({'q': address, 'format': 'json', 'limit': 1})
            url = f'https://nominatim.openstreetmap.org/search?{query}'
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Odoo20-DOLAN-Views/1.0 (LGPL-3 OpenSource)'},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    payload = json.loads(response.read().decode('utf-8'))
                    if payload:
                        rec.latitude = float(payload[0].get('lat', 0.0))
                        rec.longitude = float(payload[0].get('lon', 0.0))
                        if not rec.street_address:
                            rec.street_address = payload[0].get('display_name', address)
            except Exception as exc:
                _logger.warning('Nominatim geocoding fallback used for %s: %s', address, exc)
                if not rec.latitude and not rec.longitude:
                    rec.latitude = -34.603722
                    rec.longitude = -58.381592
        return True

    @api.model
    def get_multiview_dashboard_data(self, category_filter='all', scale='week'):
        """Return structured data for the OWL 3 Gantt, Cohort, Grid and Map views."""
        domain = []
        if category_filter and category_filter != 'all':
            domain.append(('category_type', '=', category_filter))

        items = self.search(domain, limit=250)
        today = fields.Date.context_today(self)
        start_of_week = today - timedelta(days=today.weekday())
        week_days = [(start_of_week + timedelta(days=i)) for i in range(7)]

        gantt_rows = []
        map_markers = []
        grid_map = {}

        for item in items:
            start_dt = item.date_start or fields.Datetime.now()
            stop_dt = item.date_stop or (start_dt + timedelta(days=1))
            total_days = max(1, (stop_dt.date() - start_dt.date()).days + 1)
            offset_days = (start_dt.date() - start_of_week).days
            left_pct = max(0, min(90, int(((offset_days + 3) / 14.0) * 100)))
            width_pct = max(8, min(100 - left_pct, int((total_days / 14.0) * 100)))

            gantt_rows.append({
                'id': item.id,
                'name': item.name,
                'category_type': item.category_type,
                'responsible': item.user_id.name or _('Sin asignar'),
                'partner': item.partner_id.name or '',
                'date_start': fields.Datetime.to_string(start_dt),
                'date_stop': fields.Datetime.to_string(stop_dt),
                'duration_hours': item.duration_hours,
                'progress': round(item.progress, 1),
                'state': item.state,
                'left_pct': left_pct,
                'width_pct': width_pct,
            })

            # Build Weekly Grid grouped by Responsible + Category
            group_key = f"{item.user_id.id or 0}_{item.category_type}"
            if group_key not in grid_map:
                grid_map[group_key] = {
                    'key': group_key,
                    'responsible': item.user_id.name or _('Sin asignar'),
                    'category_type': item.category_type,
                    'days': {d.isoformat(): 0.0 for d in week_days},
                    'total': 0.0,
                    'sample_item_id': item.id,
                }
            item_day = start_dt.date().isoformat()
            if item_day in grid_map[group_key]['days']:
                grid_map[group_key]['days'][item_day] = round(
                    grid_map[group_key]['days'][item_day] + item.worked_hours, 2
                )
                grid_map[group_key]['total'] = round(
                    grid_map[group_key]['total'] + item.worked_hours, 2
                )

            # Build Map Markers (from item or linked partner coordinates)
            lat = item.latitude or (item.partner_id.partner_latitude if item.partner_id else 0.0)
            lon = item.longitude or (item.partner_id.partner_longitude if item.partner_id else 0.0)
            if lat or lon or item.street_address or item.partner_id:
                partner_addr = ''
                if item.partner_id:
                    partner_addr = getattr(item.partner_id, 'contact_address', '') or item.partner_id.street or ''
                map_markers.append({
                    'id': item.id,
                    'name': item.name,
                    'partner': item.partner_id.name or _('Ubicación Operativa'),
                    'address': item.street_address or partner_addr,
                    'lat': lat or -34.6037,
                    'lon': lon or -58.3816,
                    'state': item.state,
                    'category_type': item.category_type,
                    'osm_url': f"https://www.openstreetmap.org/?mlat={lat or -34.6037}&mlon={lon or -58.3816}#map=14/{lat or -34.6037}/{lon or -58.3816}",
                })

        # Compute Cohort Retention matrix (by month of start date)
        cohort_buckets = {}
        for item in items:
            cohort_key = (item.date_start or fields.Datetime.now()).strftime('%Y-%m')
            cohort_buckets.setdefault(cohort_key, []).append(item)

        cohort_rows = []
        for period_key in sorted(cohort_buckets.keys(), reverse=True)[:6]:
            records = cohort_buckets[period_key]
            initial_count = len(records)
            periods = []
            for step in range(6):
                retained = 0
                for rec in records:
                    active_days = ((rec.date_stop or rec.date_start) - rec.date_start).days
                    if rec.state == 'done' or active_days >= step * 7 or rec.progress >= (step * 15):
                        retained += 1
                pct = round((retained / initial_count) * 100.0, 1) if initial_count else 0.0
                periods.append({'step': f'M+{step}', 'pct': pct, 'count': retained})
            cohort_rows.append({
                'cohort': period_key,
                'initial_count': initial_count,
                'periods': periods,
            })

        return {
            'gantt_rows': gantt_rows,
            'cohort_rows': cohort_rows,
            'grid_days': [d.isoformat() for d in week_days],
            'grid_rows': list(grid_map.values()),
            'map_markers': map_markers,
        }

    @api.model
    def update_item_progress(self, item_id, progress):
        item = self.browse(int(item_id))
        if item.exists():
            clamped = max(0.0, min(100.0, float(progress)))
            vals = {'progress': clamped}
            if clamped >= 100.0:
                vals['state'] = 'done'
            elif clamped > 0.0 and item.state == 'draft':
                vals['state'] = 'in_progress'
            item.write(vals)
        return True

    @api.model
    def update_grid_cell(self, item_id, date_iso, hours):
        item = self.browse(int(item_id))
        if item.exists():
            item.write({'worked_hours': max(0.0, float(hours))})
        return True
