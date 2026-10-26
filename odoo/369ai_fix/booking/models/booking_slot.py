# -*- coding: utf-8 -*-
"""Time windows the customer can book, edited by staff.

A slot is a weekday window (every Monday 09:00-12:00) or a one-off window on a date.
Two active slots for the same day and the same kind of visit may not overlap or repeat,
and a one-off slot may not overlap the weekday windows of its date.

Places in a window follow the technicians: one per employee ticked "Takes doorstep visits"
who is not off that day (technician_day_off.py). The slot's "At most" caps a window (0 = no cap).
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

WEEKDAYS = [('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), ('3', 'Thursday'),
            ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday')]
MODES = [('both', 'Doorstep & pickup'), ('doorstep', 'Doorstep only'), ('pickup', 'Pickup only')]


def _hm(value):
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return '%02d:%02d' % (hours, minutes)


class BookingSlot(models.Model):
    _name = 'fix.booking.slot'
    _description = 'Booking Time Slot'
    _order = 'date, weekday, start'

    name = fields.Char(compute='_compute_name', store=True)
    weekday = fields.Selection(WEEKDAYS, string='Every', help="Repeat every week on this day.")
    date = fields.Date('On date', help="A one-off slot on this date only (leave Every empty).")
    start = fields.Float('From', required=True, default=9.0)
    end = fields.Float('Until', required=True, default=12.0)
    capacity = fields.Integer('At most (0 = all technicians)', required=True, default=0,
                              help="Places follow the technicians who take visits and are not off that day. "
                                   "A number here caps this window; 0 = no cap.")
    mode = fields.Selection(MODES, string='For', required=True, default='both')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    @api.depends('weekday', 'date', 'start', 'end')
    def _compute_name(self):
        days = dict(WEEKDAYS)
        for slot in self:
            when = fields.Date.to_string(slot.date) if slot.date else days.get(slot.weekday, '?')
            slot.name = '%s %s-%s' % (when, _hm(slot.start), _hm(slot.end))

    def _label(self):
        return '%s-%s' % (_hm(self.start), _hm(self.end))

    @api.constrains('weekday', 'date', 'start', 'end', 'capacity', 'mode', 'active', 'company_id')
    def _check_slot(self):
        for slot in self:
            if bool(slot.weekday) == bool(slot.date):
                raise ValidationError(_("Choose either a weekday (every week) or one date."))
            if not 0 <= slot.start < 24 or not 0 < slot.end <= 24:
                raise ValidationError(_("Times must be within the day (00:00 to 24:00)."))
            if slot.end <= slot.start:
                raise ValidationError(_("%s: the end time must be after the start time.", slot.name))
            if slot.capacity < 0:
                raise ValidationError(_("%s: \"At most\" can't be below 0 (0 = all technicians).", slot.name))
            if not slot.active:
                continue
            others = self.search([('id', '!=', slot.id), ('company_id', '=', slot.company_id.id)])
            for other in others:
                if not (slot.mode == 'both' or other.mode == 'both' or slot.mode == other.mode):
                    continue
                same_day = (
                    (slot.weekday and other.weekday == slot.weekday)
                    or (slot.date and other.date == slot.date)
                    or (slot.date and other.weekday == str(slot.date.weekday()))
                    or (slot.weekday and other.date and str(other.date.weekday()) == slot.weekday)
                )
                if same_day and slot.start < other.end and other.start < slot.end:
                    raise ValidationError(_(
                        "%(slot)s overlaps %(other)s. Change the times, or archive one of them.",
                        slot=slot.name, other=other.name))

    # ------------------------------------------------------------------
    @api.model
    def _tz(self, company):
        return pytz.timezone(company.partner_id.tz or self.env.user.tz or 'Asia/Muscat')

    def _window(self, day):
        """(start, end) of this slot on `day`, as naive UTC datetimes (how Odoo stores them)."""
        self.ensure_one()
        tz = self._tz(self.company_id)

        def at(value):
            if value >= 24:
                local = datetime.combine(day + timedelta(days=1), time(0, 0))
            else:
                local = datetime.combine(day, time(int(value), int(round((value % 1) * 60)) % 60))
            return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)
        return at(self.start), at(self.end)

    def _booked(self, day):
        """Visits already holding this window (cancelled ones do not count)."""
        self.ensure_one()
        start, end = self._window(day)
        return self.env['fix.service.visit'].sudo().search_count([
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'cancelled'),
            ('slot_start', '>=', start),
            ('slot_start', '<', end),
        ])

    @api.model
    def _technicians(self, company, day):
        """Employees who can take a visit on `day`: ticked "Takes doorstep visits", in the
        company, not the website's placeholder, and without a day off then."""
        Employee = self.env['hr.employee'].sudo()
        techs = Employee.search([('fix_takes_visits', '=', True), ('company_id', '=', company.id)])
        techs -= company.sudo().wb_unassigned_employee_id
        if not techs or not day:
            return techs
        off = self.env['fix.technician.day.off'].sudo().search([
            ('employee_id', 'in', techs.ids), ('date_from', '<=', day), ('date_to', '>=', day)])
        return techs - off.employee_id

    def _places(self, day):
        """How many visits this window holds on `day`: its technicians, capped by "At most"."""
        self.ensure_one()
        places = len(self._technicians(self.company_id, day))
        return min(places, self.capacity) if self.capacity > 0 else places

    @api.model
    def _days(self, company, mode, first_day=None):
        """[(date, slots)] for the days the customer may choose from."""
        tz = self._tz(company)
        now_local = datetime.now(pytz.utc).astimezone(tz)
        days_ahead = company.wb_slot_days or 7
        earliest = datetime.now(pytz.utc).replace(tzinfo=None) + timedelta(hours=company.wb_slot_lead_hours or 0)
        start_day = max(now_local.date(), first_day or now_local.date())
        slots = self.sudo().search([('company_id', '=', company.id),
                                    ('mode', 'in', ('both', mode if mode in ('doorstep', 'pickup') else 'doorstep'))])
        out = []
        for offset in range(days_ahead):
            day = start_day + timedelta(days=offset)
            todays = slots.filtered(lambda s, d=day: s.date == d or (not s.date and s.weekday == str(d.weekday())))
            rows = []
            for slot in todays.sorted('start'):
                begin, _end = slot._window(day)
                if begin < earliest:
                    continue
                rows.append(slot)
            if rows:
                out.append((day, rows))
        return out
