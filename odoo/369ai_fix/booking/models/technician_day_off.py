# -*- coding: utf-8 -*-
"""Who can take a visit, and on which days not.

An employee ticked "Takes doorstep visits" counts as one place in every time window the
website offers (booking_slot._places). A day off takes them out of that day: one place less
in each window, and the visit is not handed to them that day (the Booking Desk asks for
someone else). Days off are a plain list (technician, from, to), not Odoo's Time Off app.
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def tick_technicians(env):
    """Staff with the Technician role take visits (on install, and the upgrade that brought this in)."""
    group = env.ref('mobile_repair.group_mobile_repair_technician', raise_if_not_found=False)
    if not group:
        return
    users = group.sudo().user_ids   # given the role itself (managers only get it through theirs)
    placeholders = env['res.company'].sudo().search([]).mapped('wb_unassigned_employee_id')
    techs = env['hr.employee'].sudo().search([('user_id', 'in', users.ids), ('fix_takes_visits', '=', False)]) - placeholders
    techs.write({'fix_takes_visits': True})


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    fix_takes_visits = fields.Boolean(
        'Takes doorstep visits', default=False,
        help="Counts as one place in every time window customers can book. Untick for staff who don't go out.")
    fix_day_off_ids = fields.One2many('fix.technician.day.off', 'employee_id', string='Days off')

    def _fix_visits_between(self, first, last):
        """This technician's visits not done or cancelled, with a time on `first`..`last` (local days)."""
        self.ensure_one()
        Slot = self.env['fix.booking.slot']
        tz = Slot._tz(self.company_id or self.env.company)

        def utc(day):
            return tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return self.env['fix.service.visit'].sudo().search([
            ('technician_id', '=', self.id), ('state', 'not in', ('done', 'cancelled')),
            ('slot_start', '>=', utc(first)), ('slot_start', '<', utc(last + timedelta(days=1)))], order='slot_start')

    def _fix_off_on(self, day):
        """Is this technician off on `day` (a date)?"""
        self.ensure_one()
        if not day:
            return False
        return bool(self.env['fix.technician.day.off'].sudo().search_count([
            ('employee_id', '=', self.id), ('date_from', '<=', day), ('date_to', '>=', day)]))


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    def _fix_free_technicians(self, exclude=None):
        """Technicians who could take this visit: they take visits, are not off that day, and have
        no other visit at that time."""
        self.ensure_one()
        visit = self.sudo()
        if not visit.slot_start:
            return self.env['hr.employee']
        company = visit.company_id or self.env.company
        Slot = self.env['fix.booking.slot']
        day = fields.Datetime.context_timestamp(visit.with_context(tz=Slot._tz(company).zone), visit.slot_start).date()
        techs = Slot._technicians(company, day) - (exclude or self.env['hr.employee'])
        end = visit.slot_end or visit.slot_start + timedelta(hours=1)
        busy = self.search([('id', '!=', visit.id), ('technician_id', 'in', techs.ids),
                            ('state', 'not in', ('done', 'cancelled')),
                            ('slot_start', '<', end), ('slot_end', '>', visit.slot_start)]).technician_id
        return (techs - busy).sorted('name')


class FixTechnicianDayOff(models.Model):
    _name = 'fix.technician.day.off'
    _description = 'Technician day off'
    _order = 'date_from desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Technician', required=True, index=True, ondelete='cascade',
                                  domain=[('fix_takes_visits', '=', True)])
    date_from = fields.Date('From', required=True, default=lambda self: fields.Date.context_today(self) + timedelta(days=1))
    date_to = fields.Date('Until', required=True, default=lambda self: fields.Date.context_today(self) + timedelta(days=1),
                          help="The last day off (the same as From for one day).")
    reason = fields.Char(required=True, help="Why, e.g. Sick leave, Annual leave, Training.")
    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    @api.model
    def _fix_create_confirm(self, vals):
        """The question before a day off is saved: who is off, which days, what it changes, and the
        visits they already have then (to give to someone else)."""
        employee = self.env['hr.employee'].sudo().browse(vals.get('employee_id') or 0).exists()
        try:
            first = fields.Date.to_date(vals.get('date_from'))
            last = fields.Date.to_date(vals.get('date_to')) or first
        except (TypeError, ValueError):
            first = last = None
        if not employee or not first or not (vals.get('reason') or '').strip():
            return ''     # the save itself says what is missing
        when = first.strftime('%a %d %b %Y') if first == last else '%s to %s' % (
            first.strftime('%a %d %b'), last.strftime('%a %d %b %Y'))
        lines = [_("%(name)s will be off on %(when)s (%(reason)s).", name=employee.name, when=when,
                   reason=vals['reason'].strip()),
                 _("Those days every time window has one place less, and no visits are given to them.")]
        visits = employee._fix_visits_between(first, last)
        if not visits:
            lines.append(_("Save this day off?"))
            return '\n\n'.join(lines)
        # they already have visits then: the pop-up asks who takes each one (_fix_after_create moves them)
        lines.append(_("They already have %s visit(s) then. Choose who takes each one:", len(visits)))
        rows = []
        for visit in visits:
            movable = visit.state in ('draft', 'assigned')
            options = visit._fix_free_technicians(exclude=employee) if movable else self.env['hr.employee']
            rows.append({
                'id': visit.id, 'name': visit.name,
                'when': fields.Datetime.context_timestamp(visit, visit.slot_start).strftime('%a %d %b, %H:%M'),
                'customer': visit.customer_name or visit.order_id.customer_name or '',
                'order': visit.order_id.name or '',
                'movable': movable,
                'options': [{'id': t.id, 'name': t.name} for t in options],
                'pick': options[:1].id or 0,
            })
        return {'title': _("Day off: %s's visits", employee.name), 'text': '\n\n'.join(lines), 'visits': rows}

    def _fix_after_create(self, extra):
        """After the day off is saved: each visit they had then goes to the technician chosen in the
        pop-up (as Assign on the desk: the job card, the visit, the new technician's link), or back
        to "To assign" on the desk when nobody was chosen."""
        picks = {str(k): v for k, v in ((extra or {}).get('reassign') or {}).items()}
        for off in self:
            employee = off.employee_id
            for visit in employee._fix_visits_between(off.date_from, off.date_to):
                if visit.state not in ('draft', 'assigned'):
                    visit.message_post(body=_("%s is off today but this visit has started: check with the office.",
                                              employee.name), subtype_xmlid='mail.mt_note')
                    continue
                tech_id = int(picks.get(str(visit.id)) or 0)
                order = visit.order_id
                try:
                    with self.env.cr.savepoint():
                        if tech_id and order:
                            order._fix_desk_assign(tech_id)
                            order.message_post(body=_("%(old)s is off (%(reason)s): the visit went to %(new)s.",
                                                      old=employee.name, reason=off.reason,
                                                      new=visit.technician_id.name))
                            continue
                        visit.sudo().write({'state': 'draft', 'assigned_on': False,
                                            'technician_id': (visit.company_id or self.env.company)
                                            .sudo().wb_unassigned_employee_id.id or False})
                        (order or visit).message_post(body=_("%(old)s is off (%(reason)s): %(visit)s is back to "
                                                             "\"To assign\" on the Booking Desk.", old=employee.name,
                                                             reason=off.reason, visit=visit.name))
                except Exception as err:  # noqa: BLE001 - the day off stands; the desk shows the visit
                    (order or visit).message_post(body=_("%(visit)s could not be moved after %(old)s's day off: %(why)s",
                                                         visit=visit.name, old=employee.name, why=err))
        return True

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and (not self.date_to or self.date_to < self.date_from):
            self.date_to = self.date_from

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for off in self:
            if off.date_to < off.date_from:
                raise ValidationError(_("%s: the last day off is before the first.", off.employee_id.name))

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_display_name(self):
        for off in self:
            when = fields.Date.to_string(off.date_from) if off.date_from == off.date_to else '%s - %s' % (
                fields.Date.to_string(off.date_from), fields.Date.to_string(off.date_to))
            off.display_name = '%s: %s' % (off.employee_id.name or '', when)
