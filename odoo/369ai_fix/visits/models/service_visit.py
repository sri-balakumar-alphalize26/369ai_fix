# -*- coding: utf-8 -*-
"""A technician's trip to the customer's door.

One record per visit. Staff move it along with the buttons today; the 369
Partner App will later do the same through these methods, which are the only
way in (so the app bridge stays a thin layer):

* `action_assign`, `action_on_the_way`, `_fs_arrive`, `action_start`,
  `action_done`, `action_cancel`
* `_fs_record_position`      - the technician's GPS heartbeat
* `_fs_set_customer_location` - the customer's point (website, pin, staff)
* `_fs_track_block`           - what the customer's tracking page may see
"""
import base64
import logging
import math
import secrets
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from .geo import metres, osm_embed, parse_map_link, valid_fix
from .online_message import VISIT_KEYS

_logger = logging.getLogger(__name__)

STATES = [
    ('draft', 'To assign'),
    ('assigned', 'Assigned'),
    ('on_the_way', 'On the way'),
    ('arrived', 'Arrived'),
    ('in_progress', 'Working'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
# What the customer reads for each state.
CUSTOMER_LABELS = {
    'draft': 'Finding a technician',
    'assigned': 'Technician assigned',
    'on_the_way': 'Technician on the way',
    'arrived': 'Technician has arrived',
    'in_progress': 'Repair in progress',
    'done': 'Visit completed',
    'cancelled': 'Visit cancelled',
}
# The customer's step bar: (state, label, time field).
STEPS = [
    ('assigned', 'Technician assigned', 'assigned_on'),
    ('on_the_way', 'On the way', 'departed_on'),
    ('arrived', 'Reached your place', 'arrived_on'),
    ('in_progress', 'Repair in progress', 'started_on'),
    ('done', 'Visit completed', 'done_on'),
]
OPEN_STATES = ('assigned', 'on_the_way', 'arrived', 'in_progress')
# While the technician's live point is shown to the customer.
LIVE_STATES = ('on_the_way', 'arrived')
LOCATION_SOURCES = [
    ('website', 'Website booking'),
    ('gps', 'Customer GPS'),
    ('ip', 'Approximate (internet)'),
    ('pin', 'Map pin'),
    ('link', 'Map link'),
    ('staff', 'Typed by staff'),
]
MAX_CODE_TRIES = 5
# A trail point is only added once the technician moved this far, so someone
# parked at a door leaves one point, not a hundred (the delivery app's rule).
MIN_MOVE_M = 25.0


def _iso(value):
    return fields.Datetime.to_datetime(value).isoformat() + 'Z' if value else None


class ServiceVisit(models.Model):
    _name = 'fix.service.visit'
    _description = 'Doorstep Visit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Visit', default='/', readonly=True, copy=False, index=True)
    state = fields.Selection(STATES, default='draft', required=True, tracking=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)

    # Where it came from
    order_id = fields.Many2one('online.service.order', string='Website Order', index=True,
                               ondelete='set null', tracking=True)
    site_id = fields.Many2one('online.service.site', string='Website', ondelete='set null')
    job_card_id = fields.Many2one('job.card', string='Job Card', index=True,
                                  ondelete='set null', tracking=True)

    # Customer
    partner_id = fields.Many2one('res.partner', string='Contact', tracking=True)
    customer_name = fields.Char('Customer', tracking=True)
    phone = fields.Char()
    area = fields.Char()
    address = fields.Char()
    building = fields.Char('Building / villa')
    floor_flat = fields.Char('Floor / flat')
    landmark = fields.Char()
    slot_start = fields.Datetime('Visit from', tracking=True)
    slot_end = fields.Datetime('Visit until')

    # Customer location
    customer_lat = fields.Float('Customer latitude', digits=(10, 7))
    customer_lng = fields.Float('Customer longitude', digits=(10, 7))
    customer_accuracy = fields.Float('Accuracy (m)')
    customer_location_source = fields.Selection(LOCATION_SOURCES, string='Location from')
    customer_location_on = fields.Datetime('Location set on')
    customer_map_link = fields.Char(
        'Paste a map link',
        help="Paste a Google Maps / WhatsApp location link (or type 'lat, lng') to set the "
             "customer's point.")
    customer_map_url = fields.Char('Customer on map', compute='_compute_maps')
    customer_map_html = fields.Html('Customer map', compute='_compute_maps', sanitize=False)

    # Technician
    technician_id = fields.Many2one('hr.employee', string='Technician', tracking=True,
                                    index=True)
    technician_user_id = fields.Many2one('res.users', related='technician_id.user_id',
                                         store=True, index=True, string='Technician user')
    technician_phone = fields.Char("Technician's phone", compute='_compute_technician_info')
    technician_image = fields.Binary('Photo', compute='_compute_technician_info')
    agent_ref = fields.Char(
        'Partner App agent', copy=False,
        help="The 369 Partner App agent doing this visit. Filled by the app link (coming later).")

    # Technician's live position (written by _fs_record_position)
    tech_lat = fields.Float('Latitude', digits=(10, 7), readonly=True, copy=False)
    tech_lng = fields.Float('Longitude', digits=(10, 7), readonly=True, copy=False)
    tech_accuracy = fields.Float('Position accuracy (m)', readonly=True, copy=False)
    tech_heading = fields.Float('Heading (°)', readonly=True, copy=False)
    tech_speed = fields.Float('Speed (m/s)', readonly=True, copy=False)
    tech_battery = fields.Float('Battery', readonly=True, copy=False,
                                help="0 to 1, as the phone reported it.")
    tech_fix_on = fields.Datetime('Position at', readonly=True, copy=False)
    start_lat = fields.Float('Set off from (lat)', digits=(10, 7), readonly=True, copy=False)
    start_lng = fields.Float('Set off from (lng)', digits=(10, 7), readonly=True, copy=False)
    tech_fix_age_s = fields.Integer('Position age (s)', compute='_compute_live')
    tech_stale = fields.Boolean('Signal lost', compute='_compute_live')
    tech_map_url = fields.Char('Technician on map', compute='_compute_maps')
    tech_map_html = fields.Html('Technician map', compute='_compute_maps', sanitize=False)
    directions_url = fields.Char('Directions', compute='_compute_maps')
    position_ids = fields.One2many('fix.service.visit.position', 'visit_id', string='Trail')

    # Distance / ETA (straight line)
    distance_km = fields.Float('Distance (km)', digits=(12, 2), compute='_compute_live')
    eta_minutes = fields.Integer('ETA (min)', compute='_compute_live')
    eta_at = fields.Datetime('Expected at', compute='_compute_live')
    arrived_distance_m = fields.Float('Distance at arrival (m)', readonly=True, copy=False,
                                      help="How far the technician's last position was from the "
                                           "customer's point when Arrived was confirmed.")

    # Steps
    assigned_on = fields.Datetime(readonly=True, copy=False)
    departed_on = fields.Datetime('Set off on', readonly=True, copy=False)
    arrived_on = fields.Datetime(readonly=True, copy=False)
    started_on = fields.Datetime('Work started on', readonly=True, copy=False)
    done_on = fields.Datetime(readonly=True, copy=False)
    cancelled_on = fields.Datetime(readonly=True, copy=False)
    cancel_reason = fields.Char(tracking=True)

    # Arrival code
    arrival_code = fields.Char(
        readonly=True, copy=False, groups='mobile_repair.group_mobile_repair_receptionist',
        help="The customer sees this code on the tracking page and in WhatsApp, and reads it "
             "out to the technician at the door.")
    arrival_verified_on = fields.Datetime('Code checked on', readonly=True, copy=False)
    arrival_tries = fields.Integer('Wrong tries', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('technician_id')
    def _compute_technician_info(self):
        for visit in self:
            employee = visit.technician_id.sudo()
            visit.technician_phone = employee.mobile_phone or employee.work_phone or False
            visit.technician_image = employee.image_128 or False

    @api.depends('customer_lat', 'customer_lng', 'tech_lat', 'tech_lng', 'tech_fix_on')
    def _compute_maps(self):
        for visit in self:
            cust = visit._fs_customer_point()
            tech = visit._fs_tech_point()
            visit.customer_map_url = (
                'https://www.google.com/maps/search/?api=1&query=%.6f,%.6f' % cust) if cust else False
            visit.tech_map_url = (
                'https://www.google.com/maps/search/?api=1&query=%.6f,%.6f' % tech) if tech else False
            if cust and tech:
                visit.directions_url = (
                    'https://www.google.com/maps/dir/?api=1&origin=%.6f,%.6f&destination=%.6f,%.6f'
                    % (tech + cust))
            elif cust:
                # Opened on the technician's phone: from wherever they are.
                visit.directions_url = 'https://www.google.com/maps/dir/?api=1&destination=%.6f,%.6f' % cust
            else:
                visit.directions_url = False
            visit.customer_map_html = self._fs_iframe(cust)
            visit.tech_map_html = self._fs_iframe(tech)

    @api.depends('customer_lat', 'customer_lng', 'tech_lat', 'tech_lng', 'tech_fix_on', 'state',
                 'company_id.fs_speed_kmh', 'company_id.fs_stale_after_s')
    def _compute_live(self):
        now = fields.Datetime.now()
        for visit in self:
            cust = visit._fs_customer_point()
            tech = visit._fs_tech_point()
            age = int((now - visit.tech_fix_on).total_seconds()) if tech else 0
            visit.tech_fix_age_s = max(age, 0)
            visit.tech_stale = bool(tech) and age > (visit.company_id.fs_stale_after_s or 120)
            km = metres(*tech, *cust) / 1000.0 if (cust and tech) else 0.0
            visit.distance_km = round(km, 2)
            minutes = 0
            if km and visit.state == 'on_the_way':
                speed = visit.company_id.fs_speed_kmh or 30.0
                minutes = max(1, math.ceil(km / speed * 60))
            visit.eta_minutes = minutes
            visit.eta_at = now + timedelta(minutes=minutes) if minutes else False

    def _fs_customer_point(self):
        self.ensure_one()
        return valid_fix(self.customer_lat, self.customer_lng)

    def _fs_tech_point(self):
        self.ensure_one()
        return valid_fix(self.tech_lat, self.tech_lng) if self.tech_fix_on else None

    @api.model
    def _fs_iframe(self, point):
        if not point:
            return False
        return Markup('<iframe src="%s" style="width:100%%;height:280px;border:0;border-radius:6px" '
                      'loading="lazy" referrerpolicy="no-referrer"></iframe>') % osm_embed(*point)

    # ------------------------------------------------------------------
    # Create / write
    # ------------------------------------------------------------------
    @api.model
    def _fs_link_vals(self, link):
        """Customer-point values from a pasted map link, or {}."""
        fix = parse_map_link(link)
        if not fix:
            return {}
        return {'customer_lat': fix[0], 'customer_lng': fix[1], 'customer_accuracy': 0.0,
                'customer_location_source': 'link', 'customer_location_on': fields.Datetime.now()}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('fix.service.visit') or '/'
            if vals.get('customer_map_link') and 'customer_lat' not in vals:
                vals.update(self._fs_link_vals(vals['customer_map_link']))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('customer_map_link') and 'customer_lat' not in vals:
            vals = dict(vals, **self._fs_link_vals(vals['customer_map_link']))
        return super().write(vals)

    @api.onchange('customer_map_link')
    def _onchange_customer_map_link(self):
        if not self.customer_map_link:
            return
        vals = self._fs_link_vals(self.customer_map_link)
        if vals:
            self.update(vals)
            return
        return {'warning': {
            'title': _("No location in that link"),
            'message': _("Paste a link that shows a pin (Google Maps 'Share' link with "
                         "coordinates, a WhatsApp location) or type 'latitude, longitude'."),
        }}

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _fs_require(self, states):
        for visit in self:
            if visit.state not in states:
                raise UserError(_("Visit %(visit)s is %(state)s; this step is not possible now.",
                                  visit=visit.name, state=dict(STATES)[visit.state]))

    @api.model
    def _fs_new_code(self):
        return '%04d' % secrets.randbelow(10000)

    def action_assign(self):
        self._fs_require(('draft',))
        for visit in self:
            if not visit.technician_id:
                raise UserError(_("Choose the technician first."))
            visit.sudo().write({
                'state': 'assigned',
                'assigned_on': fields.Datetime.now(),
                'arrival_code': visit.sudo().arrival_code or self._fs_new_code(),
                'arrival_tries': 0,
            })
            visit._fs_notify('tech_assigned')
        return True

    def action_on_the_way(self):
        self._fs_require(('assigned',))
        for visit in self:
            vals = {'state': 'on_the_way', 'departed_on': fields.Datetime.now()}
            start = visit._fs_tech_point()
            if start:
                vals.update(start_lat=start[0], start_lng=start[1])
            visit.write(vals)
            visit._fs_notify('on_the_way')
        return True

    def action_arrived(self):
        """The button: asks for the customer's code first when settings say so."""
        self.ensure_one()
        self._fs_require(('assigned', 'on_the_way'))
        if self.company_id.fs_arrival_otp and not self.arrival_verified_on:
            return {
                'type': 'ir.actions.act_window',
                'name': _("Customer's arrival code"),
                'res_model': 'fix.service.visit.arrival',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_visit_id': self.id},
            }
        result = self._fs_arrive(skip_code=True)
        if not result['ok']:
            raise UserError(result.get('message') or _("Could not mark the visit as arrived."))
        return True

    def _fs_arrive(self, code=None, latitude=None, longitude=None, skip_code=False):
        """Mark the technician at the door. Never raises for a wrong code, so the
        try counter is kept; returns {'ok', 'error'?, 'message'?, 'tries_left'?}."""
        self.ensure_one()
        visit = self.sudo()
        if visit.state not in ('assigned', 'on_the_way'):
            return {'ok': False, 'error': 'state', 'message': _("This visit is %s.") % dict(STATES)[visit.state]}
        need_code = visit.company_id.fs_arrival_otp and not visit.arrival_verified_on and not skip_code
        if need_code:
            if visit.arrival_tries >= MAX_CODE_TRIES:
                return {'ok': False, 'error': 'locked', 'tries_left': 0,
                        'message': _("Too many wrong codes. The office can confirm the arrival.")}
            if not code or str(code).strip() != (visit.arrival_code or ''):
                visit.arrival_tries += 1
                left = MAX_CODE_TRIES - visit.arrival_tries
                return {'ok': False, 'error': 'wrong_code', 'tries_left': left,
                        'message': _("Wrong code. %s tries left.") % left}
        if latitude is not None and longitude is not None:
            visit._fs_record_position(latitude, longitude)
        now = fields.Datetime.now()
        vals = {'state': 'arrived', 'arrived_on': now}
        if need_code:
            vals['arrival_verified_on'] = now
        cust, tech = visit._fs_customer_point(), visit._fs_tech_point()
        if cust and tech:
            vals['arrived_distance_m'] = round(metres(*tech, *cust), 1)
        visit.write(vals)
        if skip_code and visit.company_id.fs_arrival_otp and not visit.arrival_verified_on:
            visit.message_post(body=_("Arrival confirmed by %s without the customer's code.")
                               % self.env.user.name, subtype_xmlid='mail.mt_note')
        visit._fs_notify('arrived')
        return {'ok': True}

    def action_start(self):
        self._fs_require(('arrived',))
        self.write({'state': 'in_progress', 'started_on': fields.Datetime.now()})
        return True

    def action_done(self):
        self._fs_require(('arrived', 'in_progress'))
        self.write({'state': 'done', 'done_on': fields.Datetime.now()})
        return True

    def action_cancel(self):
        self._fs_require(('draft',) + OPEN_STATES)
        self.write({'state': 'cancelled', 'cancelled_on': fields.Datetime.now()})
        return True

    def action_reset(self):
        self._fs_require(('cancelled',))
        self.sudo().write({
            'state': 'draft', 'assigned_on': False, 'departed_on': False, 'arrived_on': False,
            'started_on': False, 'done_on': False, 'cancelled_on': False,
            'arrival_verified_on': False, 'arrival_tries': 0, 'arrival_code': False,
        })
        return True

    def _fs_form_action(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _("Doorstep Visit"),
                'res_model': 'fix.service.visit', 'res_id': self.id,
                'view_mode': 'form', 'target': 'current'}

    def action_open_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'online.service.order',
                'res_id': self.order_id.id, 'view_mode': 'form', 'target': 'current'}

    def action_open_job_card(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'job.card',
                'res_id': self.job_card_id.id, 'view_mode': 'form', 'target': 'current'}

    # ------------------------------------------------------------------
    # Job card -> visit (the technician is plainly there once work starts)
    # ------------------------------------------------------------------
    def _fs_on_job_card_state(self, job_card_state):
        now = fields.Datetime.now()
        for visit in self.sudo():
            if job_card_state in ('inspection', 'quotation', 'repair') \
                    and visit.state in ('assigned', 'on_the_way', 'arrived'):
                visit.write({'state': 'in_progress', 'started_on': now,
                             'arrived_on': visit.arrived_on or now})
            elif job_card_state == 'completed' and visit.state in OPEN_STATES:
                visit.write({'state': 'done', 'done_on': now,
                             'arrived_on': visit.arrived_on or now})
            elif job_card_state == 'cancelled' and visit.state in ('draft', 'assigned', 'on_the_way'):
                visit.write({'state': 'cancelled', 'cancelled_on': now,
                             'cancel_reason': visit.cancel_reason or _("Job card cancelled")})

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------
    def _fs_record_position(self, latitude, longitude, accuracy=None, heading=None,
                            speed=None, battery=None):
        """The technician's position. Updates the visit's live point and adds a
        trail point after a 25 m move. False for a bad fix or a closed visit."""
        self.ensure_one()
        fix = valid_fix(latitude, longitude)
        visit = self.sudo()
        if not fix or visit.state not in OPEN_STATES:
            return False

        def num(value):
            try:
                return float(value or 0.0)
            except (TypeError, ValueError):
                return 0.0

        now = fields.Datetime.now()
        visit.write({
            'tech_lat': fix[0], 'tech_lng': fix[1], 'tech_fix_on': now,
            'tech_accuracy': num(accuracy), 'tech_heading': num(heading),
            'tech_speed': num(speed), 'tech_battery': num(battery),
        })
        Position = self.env['fix.service.visit.position'].sudo()
        last = Position.search([('visit_id', '=', visit.id)], limit=1)
        if last and metres(last.latitude, last.longitude, *fix) < MIN_MOVE_M:
            return True
        Position.create({'visit_id': visit.id, 'latitude': fix[0], 'longitude': fix[1],
                         'accuracy': num(accuracy), 'recorded_on': now})
        return True

    def _fs_set_customer_location(self, latitude, longitude, accuracy=None, source='staff'):
        self.ensure_one()
        fix = valid_fix(latitude, longitude)
        if not fix:
            return False
        try:
            accuracy = float(accuracy or 0.0)
        except (TypeError, ValueError):
            accuracy = 0.0
        self.sudo().write({
            'customer_lat': fix[0], 'customer_lng': fix[1], 'customer_accuracy': accuracy,
            'customer_location_source': source if source in dict(LOCATION_SOURCES) else 'staff',
            'customer_location_on': fields.Datetime.now(),
        })
        return True

    # ------------------------------------------------------------------
    # What the customer's tracking page may see
    # ------------------------------------------------------------------
    def _fs_photo_uri(self):
        self.ensure_one()
        image = self.technician_id.sudo().image_128
        if not image:
            return None
        raw = base64.b64decode(image)
        mime = guess_mimetype(raw, default='image/png')
        return 'data:%s;base64,%s' % (mime, image.decode() if isinstance(image, bytes) else image)

    def _fs_track_block(self):
        self.ensure_one()
        visit = self.sudo()
        company = visit.company_id
        active = visit.state in OPEN_STATES
        cancelled = visit.state == 'cancelled'
        index = next((i for i, step in enumerate(STEPS) if step[0] == visit.state), -1)
        out = {
            'ref': visit.name,
            'state': visit.state,
            'state_label': _(CUSTOMER_LABELS[visit.state]),
            'steps': [{'key': key, 'label': _(label), 'at': _iso(visit[field]),
                       'done': not cancelled and i <= index, 'current': not cancelled and i == index}
                      for i, (key, label, field) in enumerate(STEPS)],
            'slot': {'start': _iso(visit.slot_start), 'end': _iso(visit.slot_end)}
                    if visit.slot_start else None,
            'technician': None,
            'live': None,
            'dest': None,
            'distance_km': None,
            'eta_minutes': None,
            'eta_at': None,
            'arrival_code': None,
        }
        if visit.technician_id and visit.state not in ('draft', 'cancelled'):
            tech = {'name': visit.technician_id.name, 'phone': None, 'photo': None}
            if active:
                if company.fs_show_tech_phone:
                    tech['phone'] = visit.technician_phone or None
                tech['photo'] = visit._fs_photo_uri()
            out['technician'] = tech
        if visit.state in LIVE_STATES:
            cust, tech_point = visit._fs_customer_point(), visit._fs_tech_point()
            if cust:
                out['dest'] = {'lat': cust[0], 'lng': cust[1]}
            if tech_point:
                out['live'] = {'lat': tech_point[0], 'lng': tech_point[1],
                               'fix_on': _iso(visit.tech_fix_on), 'age_s': visit.tech_fix_age_s,
                               'stale': visit.tech_stale}
            if cust and tech_point:
                out['distance_km'] = visit.distance_km
            if visit.eta_minutes:
                out['eta_minutes'] = visit.eta_minutes
                out['eta_at'] = _iso(visit.eta_at)
        if active and company.fs_arrival_otp and visit.arrival_code and not visit.arrival_verified_on:
            out['arrival_code'] = visit.arrival_code
        return out

    # ------------------------------------------------------------------
    # WhatsApp to the customer
    # ------------------------------------------------------------------
    def _fs_notify(self, key):
        """The visit's WhatsApp message; the result goes to the visit's chatter."""
        labels = dict(VISIT_KEYS)
        for visit in self.sudo():
            order = visit.order_id
            site = visit.site_id or order.site_id
            phone = visit.phone or order.phone
            if not site or not site.whatsapp_messages or not phone:
                continue
            eta = visit.eta_minutes
            text = self.env['online.service.message']._render(key, {
                'name': visit.customer_name or order.customer_name or _("customer"),
                'order': order.name or visit.name,
                'status': labels.get(key, key),
                'job_card': visit.job_card_id.name or order.job_card_id.name or '',
                'site': site.name,
                'track_url': site._track_url(),
                'summary': order.summary or '',
                'technician': visit.technician_id.name or '',
                'technician_phone': visit.technician_phone or '',
                'eta': _("about %s min") % eta if eta else '',
                'code': visit.arrival_code or '',
            })
            if not text:
                continue
            status, detail = site._wa_send(phone, text)
            visit.message_post(
                body=_("WhatsApp to customer (%(status)s): %(result)s",
                       status=labels.get(key, key),
                       result={'sent': _("sent"), 'queued': _("queued, the gateway will retry"),
                               'blocked': _("not sent"), 'error': _("failed"),
                               'skipped': _("skipped")}.get(status, status)
                       + (' - %s' % detail if detail else '')),
                message_type='comment', subtype_xmlid='mail.mt_note')
