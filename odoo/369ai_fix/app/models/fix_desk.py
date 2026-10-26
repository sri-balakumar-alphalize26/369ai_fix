# -*- coding: utf-8 -*-
"""The Booking Desk: one screen that carries a website booking from new to done.

new -> approve / call / reject -> time booked -> assign the technician -> live visit
on the map -> done. Everything here reads and calls what the other parts already
have (booking/, visits/, danatfix_repair_booking when it is installed); the desk
adds no field of its own.

* `fix_desk_load(stage, since)`  - stage counts, the cards of one stage, the technicians
* `fix_desk_detail()`            - everything the right-hand pane shows for one order
* `fix_desk_act(action, ...)`    - one button; wizards come back as {'action': ...}
* `_fix_desk_notify()`           - the bus message that makes every open desk refresh
"""
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.web.controllers.utils import clean_action

from ...visits.models.service_visit import OPEN_STATES, STATES as VISIT_STATES, STEPS

_logger = logging.getLogger(__name__)

BUS_CHANNEL = 'fix_desk'
BUS_TYPE = 'fix_desk/refresh'

# In the order the rail shows them: what needs a hand first.
STAGES = [
    ('new', 'New'),
    ('calling', 'Calling'),
    ('approved', 'Time to book'),
    ('booked', 'Time booked'),
    ('to_assign', 'To assign'),
    ('assigned', 'Assigned'),
    ('live', 'Live'),
    ('working', 'Working'),
    ('done_today', 'Done today'),
    ('rejected', 'Rejected'),
]
WORKING_CARD_STATES = ('inspection', 'quotation', 'repair')
PARTS_BADGES = {'ask': 'Parts: customer asked', 'ordering': 'Parts on order'}
MAX_ORDERS = 500
# The two alarms (new booking, visit time booked): on/off, ring and pause in seconds.
DEFAULT_SOUND = {'new_on': True, 'ring': 20, 'repeat': 15,
                 'slot_on': True, 'slot_ring': 20, 'slot_repeat': 15}
MAX_TRAIL = 400


def _today_start():
    return fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _dt(value):
    return fields.Datetime.to_string(value) if value else False


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    # ------------------------------------------------------------------
    # Bus: every open desk refreshes at once
    # ------------------------------------------------------------------
    @api.model
    def _fix_desk_notify(self):
        try:
            self.env['bus.bus']._sendone(BUS_CHANNEL, BUS_TYPE, {})
        except Exception as err:  # noqa: BLE001 - the 20 s poll catches up
            _logger.warning("Booking Desk: bus notify failed: %s", err)

    def _ring(self):
        """Every existing ring (new order, opened, approved, slot booked, ...) also wakes the desk."""
        res = super()._ring()
        self._fix_desk_notify()
        return res

    # ------------------------------------------------------------------
    # Settings (danatfix when it is installed, else the plain defaults)
    # ------------------------------------------------------------------
    @api.model
    def _fix_desk_settings(self):
        if 'danatfix.booking.settings' in self.env:
            settings = self.env['danatfix.booking.settings'].get_settings()
            sound = settings._alarm_sound() if hasattr(settings, '_alarm_sound') else {
                'ring': max(3, settings.ring_seconds or 20), 'repeat': max(3, settings.repeat_seconds or 15)}
            return dict(DEFAULT_SOUND, **sound,
                        poll_ready=bool(settings.poll_enabled and settings._group_jid()))
        return dict(DEFAULT_SOUND, poll_ready=False)

    @api.model
    def _fix_desk_technicians(self):
        """Employees who can take a visit: with a phone or a login, minus the placeholder."""
        Employee = self.env['hr.employee'].sudo()
        placeholders = self.env.companies.sudo().mapped('wb_unassigned_employee_id')
        employees = Employee.search([
            ('company_id', 'in', self.env.companies.ids),
            '|', '|', ('user_id', '!=', False), ('mobile_phone', '!=', False), ('work_phone', '!=', False),
        ], order='name')
        # their coming days off, so the assign list leaves out who is off on the booking's day
        today = fields.Date.context_today(self)
        off = {}
        for day_off in self.env['fix.technician.day.off'].sudo().search(
                [('employee_id', 'in', employees.ids), ('date_to', '>=', today)]):
            day = max(day_off.date_from, today)
            while day <= day_off.date_to and day <= today + timedelta(days=90):
                off.setdefault(day_off.employee_id.id, []).append(fields.Date.to_string(day))
                day += timedelta(days=1)
        return [{'id': e.id, 'name': e.name, 'phone': e.mobile_phone or e.work_phone or '',
                 'takes_visits': e.fix_takes_visits, 'off': off.get(e.id, [])}
                for e in employees if e not in placeholders]

    # ------------------------------------------------------------------
    # Stage of one order
    # ------------------------------------------------------------------
    def _fix_desk_placeholder(self):
        self.ensure_one()
        return (self.company_id or self.env.company).sudo().wb_unassigned_employee_id

    def _fix_desk_cards(self):
        self.ensure_one()
        return self.sudo().job_card_ids.filtered(lambda c: c.state != 'cancelled')

    def _fix_desk_visit(self):
        """The visit that counts (newest not cancelled), as sudo, or an empty one."""
        self.ensure_one()
        return self.sudo()._fs_current_visit()

    def _fix_desk_stage(self, today=None):
        """Which column of the desk this order is in, or None when the desk does not show it."""
        self.ensure_one()
        order = self.sudo()
        today = today or _today_start()
        if order.state == 'cancelled':
            return 'rejected' if order.rejected and order.rejected_on and order.rejected_on >= today else None
        if order.state == 'new':
            return 'calling' if getattr(order, 'desk_calling', False) else 'new'
        visit = order._fs_current_visit()
        cards = order._fix_desk_cards()
        if order.state == 'done':
            return 'done_today' if order.done_on and order.done_on >= today else None
        # confirmed
        if order.slot_booked_on and not order.slot_seen_by_id:
            return 'booked'
        vstate = visit.state if visit else False
        if vstate in ('on_the_way', 'arrived'):
            return 'live'
        if vstate == 'in_progress' or any(c.state in WORKING_CARD_STATES for c in cards):
            return 'working'
        if vstate == 'assigned':
            return 'assigned'
        if vstate == 'done':
            return 'done_today' if visit.done_on and visit.done_on >= today else None
        if not order.slot_id:
            return 'approved'
        placeholder = order._fix_desk_placeholder()
        if order.mode != 'doorstep' and cards and all(c.assigned_to and c.assigned_to != placeholder for c in cards):
            return 'assigned'
        return 'to_assign'

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    @api.model
    def _fix_desk_domain(self, today):
        return [
            ('company_id', 'in', self.env.companies.ids),
            '|', '|',
            ('state', 'in', ('new', 'confirmed')),
            '&', ('state', '=', 'cancelled'), ('rejected_on', '>=', today),
            '&', ('state', '=', 'done'), ('done_on', '>=', today),
        ]

    @api.model
    def _fix_desk_stamp(self, orders):
        """Changes whenever an order, its visits, its trail or its job cards changed."""
        orders = orders.sudo()
        visits = orders.visit_ids
        cards = orders.job_card_ids
        return '%s|%s|%s|%d' % (
            _dt(max(orders.mapped('write_date'), default=None)),
            _dt(max(visits.mapped('write_date'), default=None)),
            _dt(max(cards.mapped('write_date'), default=None)),
            len(orders),
        )

    @api.model
    def fix_desk_load(self, stage='new', since=None):
        """Counts for every stage, the cards of `stage` (None when nothing changed since
        `since`), the technicians and the alarm settings."""
        today = _today_start()
        orders = self.search(self._fix_desk_domain(today), order='id asc', limit=MAX_ORDERS)
        staged = {key: self.browse() for key, _label in STAGES}
        for order in orders:
            key = order._fix_desk_stage(today)
            if key:
                staged[key] |= order
        stamp = self._fix_desk_stamp(orders)
        if stage not in staged:
            stage = 'new'
        rows = None
        if not since or since != stamp:
            rows = [order._fix_desk_row(stage, today) for order in staged[stage]]
        data = {
            'stages': [{'key': key, 'label': _(label)} for key, label in STAGES],
            'stage': stage,
            'counts': {key: len(recs) for key, recs in staged.items()},
            'rows': rows,
            'since': stamp,
            'technicians': self._fix_desk_technicians(),
            'now': _dt(fields.Datetime.now()),
            'has_calling': 'desk_calling' in self._fields,
        }
        data.update(self._fix_desk_settings())
        return data

    def _fix_desk_row(self, stage=None, today=None):
        """One card of the list."""
        self.ensure_one()
        order = self.sudo()
        stage = stage or order._fix_desk_stage(today)
        visit = order._fs_current_visit()
        cards = order._fix_desk_cards()
        _text, total = order._wb_estimate()
        technician = visit.technician_id if visit and visit.state not in ('draft', 'cancelled') else None
        if not technician and cards:
            placeholder = order._fix_desk_placeholder()
            technician = next((c.assigned_to for c in cards if c.assigned_to and c.assigned_to != placeholder), None)
        numbers = order._wb_numbers()
        return {
            'id': order.id,
            'name': order.name,
            'stage': stage,
            'state': order.state,
            'mode': order.mode,
            'mode_label': dict(order._fields['mode'].selection).get(order.mode, ''),
            'customer': order.customer_name or '',
            'phone_digits': _digits(numbers[0][1]) if numbers else '',
            'area': order.area or '',
            'summary': order.summary or '',
            'slot': order.slot_label or '',
            'slot_unseen': bool(order.slot_booked_on and not order.slot_seen_by_id),
            'total': total,
            'currency': (order.company_id or self.env.company).currency_id.name,
            'parts_badge': _(PARTS_BADGES[order.parts_state]) if order.parts_state in PARTS_BADGES else '',
            'technician': technician.name if technician else '',
            'stale': bool(visit and visit.state in OPEN_STATES and visit.tech_stale),
            'eta': visit.eta_minutes if visit and visit.state == 'on_the_way' else 0,
            'visit_state': visit.state if visit else '',
            'visit_label': dict(VISIT_STATES).get(visit.state, '') if visit else '',
            'card_state': cards[:1].state if cards else '',
            'at_office': any(cards.mapped('wb_at_office')),
            'calling_by': getattr(order, 'desk_calling_by', '') or '',
            'reject_pending': bool(getattr(order, 'desk_reject_pending', False)),
            'needs_screen': getattr(order, 'desk_needs_screen', '') or '',
            'poll_error': bool(getattr(order, 'poll_error', '')),
            'created': _dt(order.create_date),
        }

    # ------------------------------------------------------------------
    # Detail pane
    # ------------------------------------------------------------------
    def _fix_desk_actions(self, stage, visit, cards):
        """The buttons this stage offers, in the order they are shown."""
        self.ensure_one()
        order = self.sudo()
        receptionist = self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist')
        if stage == 'new':
            return ['reject'] if getattr(order, 'desk_reject_pending', False) else ['approve', 'call', 'reject']
        if stage == 'calling':
            return ['approve', 'reject']
        if stage == 'approved':
            # no time yet: the customer picks one from their link or My orders, or staff book it here
            # (on the phone); the technician gets the link with the time (booking/)
            return ['book_time', 'call']
        if stage == 'booked':
            return ['seen', 'call']
        if stage == 'to_assign':
            return ['assign', 'call']
        if stage == 'assigned':
            return ['on_the_way', 'send_link', 'assign', 'cancel_visit', 'call']
        if stage == 'live':
            if visit and visit.state == 'on_the_way':
                acts = ['arrived']
                if visit.company_id.fs_arrival_otp and receptionist:
                    acts.append('arrived_skip')
                return acts + ['send_link', 'cancel_visit', 'call']
            acts = ['start', 'done']
            if cards.filtered(lambda c: c.state in ('inspection', 'quotation') and not c.wb_at_office):
                acts.append('office')
            return acts + ['call']
        if stage == 'working':
            acts = []
            if visit and visit.state == 'in_progress' and visit.close_stage == 'finish':
                # repair done: the technician takes the photo, the payment and the customer's code
                manager = self.env.user.has_group('mobile_repair.group_mobile_repair_manager')
                return (['finish_skip'] if manager else []) + ['call']
            if visit and visit.state == 'in_progress':
                # what the technician found -> the quotation first -> the customer's OK (visits/visit_result.py)
                acts += {
                    'waiting': ['approved_here', 'declined_here', 'later'],
                    'repairing': ['repair_done'],
                    'to_take': ['take'],
                }.get(visit.check_result, ['check_result', 'fixed'])
                if visit.check_result in ('waiting', 'repairing', 'to_take'):
                    return acts + ['call']
            if cards.filtered(lambda c: c.state in ('inspection', 'quotation') and not c.wb_at_office):
                acts.append('office')
            return acts + ['call']
        return []

    def _fix_desk_timeline(self, visit):
        if not visit or visit.state in ('draft', 'cancelled'):
            return []
        index = next((i for i, step in enumerate(STEPS) if step[0] == visit.state), -1)
        return [{'key': key, 'label': _(label), 'at': _dt(visit[field]),
                 'done': i <= index, 'current': i == index}
                for i, (key, label, field) in enumerate(STEPS)]

    def _fix_desk_map(self, visit):
        if not visit or visit.state in ('draft', 'cancelled'):
            return None
        cust = visit._fs_customer_point()
        tech = visit._fs_tech_point()
        positions = visit.position_ids.sorted('recorded_on')[-MAX_TRAIL:]
        return {
            'customer': {'lat': cust[0], 'lng': cust[1]} if cust else None,
            'tech': {'lat': tech[0], 'lng': tech[1], 'fix_on': _dt(visit.tech_fix_on),
                     'age_s': visit.tech_fix_age_s, 'stale': visit.tech_stale,
                     'accuracy': visit.tech_accuracy, 'speed': visit.tech_speed,
                     'battery': visit.tech_battery} if tech else None,
            'start': {'lat': visit.start_lat, 'lng': visit.start_lng} if visit.start_lat or visit.start_lng else None,
            'trail': [[p.latitude, p.longitude] for p in positions],
            'distance_km': visit.distance_km if (cust and tech) else 0.0,
            'eta_minutes': visit.eta_minutes,
            'eta_at': _dt(visit.eta_at),
            'live': visit.state in OPEN_STATES,
        }

    def _fix_desk_prize(self):
        """The Spin & Win prize on this booking, else the customer's prize still to be used
        (so the desk can remind them); None when there is none or the wheel is switched off."""
        self.ensure_one()
        order = self.sudo()
        win = order.spin_win_id or (order.partner_id._spin_current_win() if order.partner_id else None)
        if not win or not win.site_id.wheel_show:
            return None
        return {'id': win.id, 'prize': win.prize or '', 'code': win.code, 'given': bool(win.given_on),
                'on_booking': win == order.spin_win_id,
                'valid_until': fields.Date.to_string(win.valid_until) if win.valid_until else ''}

    def fix_desk_detail(self):
        """Everything the detail pane shows for this order."""
        self.ensure_one()
        order = self.sudo()
        today = _today_start()
        stage = order._fix_desk_stage(today)
        visit = order._fs_current_visit()
        cards = order._fix_desk_cards()
        company = order.company_id or self.env.company
        currency = company.currency_id
        estimate, total = order._wb_estimate()
        missing = order._wb_missing_parts()
        Attachment = self.env['ir.attachment'].sudo()
        holders = [('res_model', '=', 'job.card'), ('res_id', 'in', cards.ids)] if cards else [
            ('res_model', '=', 'online.service.order'), ('res_id', '=', order.id)]
        photos = Attachment.search(holders + [('mimetype', 'like', 'image/')], limit=8)
        video_ids = Attachment.search(holders + [('mimetype', 'like', 'video/')], limit=3).ids
        receptionist = self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist')
        card_states = dict(self.env['job.card']._fields['state'].selection)
        quote_states = dict(self.env['job.card']._fields['quote_state'].selection) \
            if 'quote_state' in self.env['job.card']._fields else {}
        row = order._fix_desk_row(stage, today)
        row.update({
            'stage_label': _(dict(STAGES)[stage]) if stage else '',
            'state_label': dict(order._fields['state'].selection).get(order.state, ''),
            'numbers': [{'label': label, 'number': number, 'digits': _digits(number)}
                        for label, number in order._wb_numbers()],
            'address': order.address or '',
            'map_url': order.map_url or '',
            'email': order.email or '',
            'problem': order.problem or '',
            'note': order.note or '',
            'prize': order._fix_desk_prize(),
            'slot_date': fields.Date.to_string(order.slot_date) if order.slot_date else '',
            'lines': [{'id': l.id, 'device': l.device or '', 'model': l.model or '', 'issue': l.issue or '',
                       'qty': l.qty or 1, 'price': l.product_id.lst_price if l.product_id else None}
                      for l in order.line_ids],
            'estimate': estimate.split('\n'),
            'parts': [{'name': l.description or l.product_id.display_name, 'qty': l.quantity,
                       'on_hand': l.product_id.qty_available, 'missing': l in missing}
                      for l in cards.spare_part_line_ids],
            'parts_state': order.parts_state,
            'parts_state_label': dict(order._fields['parts_state'].selection).get(order.parts_state, ''),
            'parts_days': order.parts_days,
            'photos': photos.ids,
            'videos': len(video_ids),
            'video_ids': video_ids,       # played in the desk (a preview that opens the video)
            'job_cards': [{'id': c.id, 'name': c.name, 'state': c.state, 'state_label': card_states.get(c.state, c.state),
                           'quote': (quote_states.get(c.quote_state, '')
                                     if getattr(c, 'quote_state', 'none') not in ('none', False) else ''),
                           'at_office': bool(getattr(c, 'wb_at_office', False)),
                           'return_by': fields.Date.to_string(c.wb_return_by) if getattr(c, 'wb_return_by', False) else '',
                           'technician': c.assigned_to.name if c.assigned_to and c.assigned_to != order._fix_desk_placeholder() else ''}
                          for c in cards],
            'approved_on': _dt(order.approved_on),
            'approved_by': order.approved_by_id.name or '',
            'slot_booked_on': _dt(order.slot_booked_on),
            'slot_seen_by': order.slot_seen_by_id.name or '',
            'reject_reason': order.reject_reason or '',
            'rejected_by': _("the customer") if order.rejected_by_customer else (order.rejected_by_id.name or ''),
            'poll_sent': bool(getattr(order, 'poll_sent', False)),
            'poll_error_text': getattr(order, 'poll_error', '') or '',
            'opened_by': order.opened_by_id.name or '',
            'actions': order._fix_desk_actions(stage, visit, cards),
            # what the customer and the technician got on WhatsApp, oldest first (the WhatsApp tab)
            'whatsapp': self.env['online.service.wa.message'].sudo().search(
                [('order_id', '=', order.id)], order='id desc', limit=100)[::-1]._desk_rows(),
            'visit': None,
            'map': None,
        })
        if visit:
            tech = visit.technician_id
            row['visit'] = {
                'id': visit.id,
                'name': visit.name,
                'state': visit.state,
                'state_label': dict(VISIT_STATES).get(visit.state, visit.state),
                'result_label': (dict(visit._fields['check_result'].selection).get(visit.check_result, '')
                                 if 'check_result' in visit._fields and visit.check_result else ''),
                'technician_id': tech.id or False,
                'technician': tech.name or '',
                'technician_phone': visit.technician_phone or '',
                'slot_start': _dt(visit.slot_start),
                'slot_end': _dt(visit.slot_end),
                'timeline': order._fix_desk_timeline(visit),
                'link_sent_on': _dt(visit.tech_link_sent_on),
                'link_until': _dt(visit.tech_token_until),
                'arrival_code': (visit.arrival_code if receptionist and company.fs_arrival_otp
                                 and visit.state in OPEN_STATES and not visit.arrival_verified_on else ''),
                'arrival_verified_on': _dt(visit.arrival_verified_on),
                'arrived_distance_m': visit.arrived_distance_m,
                'cancel_reason': visit.cancel_reason or '',
                # after the repair (visits/visit_closeout.py)
                'finishing': visit.close_stage == 'finish' and visit.state == 'in_progress',
                'finish_code': (visit.finish_code if receptionist and visit.close_stage == 'finish'
                                and visit.state == 'in_progress' else ''),
                'finish_missing': visit._co_missing() if visit.close_stage == 'finish' else [],
                'paid_text': visit._co_paid_text() if visit.paid_on else '',
                'warranty_until': fields.Date.to_string(visit.warranty_until) if visit.warranty_until else '',
                'rating': visit.rating or 0,
                'rating_note': visit.rating_note or '',
                'outcome_label': (dict(visit._fields['check_outcome'].selection).get(visit.check_outcome, '')
                                  if visit.check_outcome else ''),
                'stale': visit.tech_stale,
                'fix_age_s': visit.tech_fix_age_s,
                'directions_url': visit.directions_url or '',
            }
            row['map'] = order._fix_desk_map(visit)
        return row

    # ------------------------------------------------------------------
    # One button
    # ------------------------------------------------------------------
    def _fix_desk_require_visit(self):
        visit = self._fix_desk_visit()
        if not visit or visit.state in ('cancelled',):
            raise UserError(_("%s has no open visit.", self.name))
        return visit

    def _fix_desk_assign(self, technician_id):
        """Technician on the job cards (where the placeholder still is) and on the visit;
        a draft visit is assigned (customer WhatsApp + technician link), an open one gets
        the link again when the technician changed."""
        self.ensure_one()
        technician = self.env['hr.employee'].sudo().browse(int(technician_id or 0)).exists()
        if not technician:
            raise UserError(_("Choose the technician first."))
        order = self.sudo()
        if order.state != 'confirmed':
            raise UserError(_("Approve %s before assigning a technician.", order.name))
        placeholder = order._fix_desk_placeholder()
        # a technician on a day off (Configuration > Days Off) does not get that day's visit
        day = getattr(order, 'slot_date', False)
        if day and technician._fix_off_on(day):
            raise UserError(_("%(tech)s is off on %(day)s: choose another technician.",
                              tech=technician.name, day=day.strftime('%a %d %b')))
        cards = order.job_card_ids.filtered(lambda c: c.state not in ('completed', 'cancelled'))
        cards.filtered(lambda c: not c.assigned_to or c.assigned_to == placeholder or c.state == 'draft') \
            .write({'assigned_to': technician.id})
        if order.mode != 'doorstep' and not order.visit_ids:
            order.message_post(body=_("Technician %s assigned from the Booking Desk.", technician.name))
            return
        visit = order._fs_current_visit()
        if not visit or visit.state in ('done', 'cancelled'):
            visit = self.env['fix.service.visit'].sudo().create(order._fs_visit_vals())
        changed = visit.technician_id != technician
        if changed:
            visit.write({'technician_id': technician.id})
        if visit.state == 'draft':
            visit.action_assign()
        elif changed and visit.state in OPEN_STATES:
            visit.message_post(body=_("Technician changed to %s from the Booking Desk.", technician.name))
            visit._fs_send_tech_link()

    def fix_desk_act(self, action, stage='new', technician_id=None, reason=None, **kw):
        """A button on the desk. Wizards (approve, reject, arrival code, office, call with two
        numbers) come back as {'action': ...}; everything else returns the refreshed desk with
        this order's detail."""
        self.ensure_one()
        warning = ''
        # A wizard action goes to the web client as it is, so it needs the clean-up a form
        # button gets from the server (its 'views' list above all).
        wizard = lambda act: {'action': clean_action(act, self.env)}  # noqa: E731
        if action == 'approve':
            self.action_mark_opened()
            return wizard(self.action_wb_approve())
        if action == 'reject':
            self.action_mark_opened()
            return wizard(self.action_wb_reject())
        if action == 'call':
            if hasattr(self, '_desk_set_calling'):
                _ok, warning = self._desk_set_calling(self.env.user.name)
            else:
                self.action_mark_opened()
                return wizard(self.action_wb_call())
        elif action == 'seen':
            self.action_wb_slot_seen()
        elif action == 'office':
            card = self._fix_desk_cards().filtered(
                lambda c: c.state in ('inspection', 'quotation') and not c.wb_at_office)[:1]
            if not card:
                raise UserError(_("No job card in inspection or quotation to take to the office."))
            return wizard(card.with_env(self.env).action_wb_take_to_office())
        elif action == 'assign':
            self._fix_desk_assign(technician_id)
        elif action == 'send_link':
            visit = self._fix_desk_require_visit()
            visit._fs_require(OPEN_STATES)
            status, link = visit._fs_send_tech_link()
            if status not in ('sent', 'queued'):
                warning = (_("The link was not sent on WhatsApp. Copy it from the visit's chatter.")
                           if link else _("No link: set the website's web address first."))
        elif action == 'on_the_way':
            self._fix_desk_require_visit().action_on_the_way()
        elif action == 'arrived':
            result = self._fix_desk_require_visit().action_arrived()
            if isinstance(result, dict):
                return wizard(result)
        elif action == 'arrived_skip':
            if not self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
                raise UserError(_("Only the office can confirm an arrival without the code."))
            result = self._fix_desk_require_visit()._fs_arrive(skip_code=True)
            if not result.get('ok'):
                raise UserError(result.get('message') or _("Could not mark the visit as arrived."))
        elif action == 'start':
            # opens "Before you start" while the safety check / device photos are not done
            result = self._fix_desk_require_visit().action_start()
            if isinstance(result, dict):
                return wizard(result)
        elif action == 'done':
            self._fix_desk_require_visit().action_done()
        elif action == 'check_result':
            return wizard(self._fix_desk_require_visit().action_open_result())
        elif action in ('fixed', 'repair_done'):
            self._fix_desk_require_visit()._vr_fixed()
        elif action == 'approved_here':
            self._fix_desk_require_visit()._vr_approved_here()
        elif action == 'declined_here':
            self._fix_desk_require_visit()._vr_declined_here()
        elif action == 'later':
            self._fix_desk_require_visit()._vr_decide_later()
        elif action == 'take':
            return wizard(self._fix_desk_require_visit().action_open_take())
        elif action == 'finish_skip':
            self._fix_desk_require_visit().with_env(self.env).action_finish_without_code(reason)
        elif action == 'cancel_visit':
            visit = self._fix_desk_require_visit()
            if reason:
                visit.write({'cancel_reason': reason})
            visit.action_cancel()
        else:
            raise UserError(_("Unknown action: %s", action))
        data = self.fix_desk_load(stage=stage)
        data['detail'] = self.fix_desk_detail()
        if warning:
            data['warning'] = warning
        return data


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals or 'technician_id' in vals:
            self.env['online.service.order']._fix_desk_notify()
        return res

    def _fs_record_position(self, latitude, longitude, accuracy=None, heading=None,
                            speed=None, battery=None):
        """A new trail point wakes the desks; a heartbeat from the same spot does not."""
        Position = self.env['fix.service.visit.position'].sudo()
        before = Position.search_count([('visit_id', '=', self.id)])
        res = super()._fs_record_position(latitude, longitude, accuracy=accuracy, heading=heading,
                                          speed=speed, battery=battery)
        if res and Position.search_count([('visit_id', '=', self.id)]) > before:
            self.env['online.service.order']._fix_desk_notify()
        return res
