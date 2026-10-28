# -*- coding: utf-8 -*-
"""The technician's tool bag: checked when leaving the office and when leaving each house.

One list of tools for every technician (369 ai Fix > Configuration > Tools Checklist). The
technician marks each tool "in the bag" or "missing" and takes one photo of the open bag:

* leaving the office - once a day, before the first "Start trip" of the day;
* leaving the house ("Before you leave") - shown once "Can it be fixed?" is answered, and
  needed before the technician's own steps that end the work: Fixed on the spot / Repair done, Finish,
  take the device, declined, decides later, not repaired, the office finds the part. A visit
  closed another way (the customer's link, the office) keeps its check due, and the
  technician's next "Start trip" asks for it first.

A missing tool never stops the work. It is written down, the Booking Desk shows it on the
booking where it went missing, the technician's next visits warn, and it stays open until someone marks it found
(Missing Tools) or the technician marks it in the bag again at a later check. With no tool in
the list nothing is asked.

Only the technician's own steps ask (the WhatsApp page and My Visits): the office's buttons
don't, the office cannot see the bag. A manager can skip a check with a reason (Tool Checks).
"""
import base64

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .visit_checks import PHOTO_BYTES, _sniff
from .visit_result import FEE_OUTCOMES, NO_REPAIR

KINDS = [('office', 'Leaving the office'), ('house', 'Leaving the house')]
CHECK_STATES = [('todo', 'To do'), ('done', 'Done'), ('skipped', 'Skipped')]
LINE_STATES = [('todo', 'Not ticked'), ('ok', 'In the bag'), ('missing', 'Missing')]
# the technician's steps that end the visit at the customer's door (and so wait for "Before you leave")
CLOSING = ('done', 'close_code', 'result_take', 'result_declined_here', 'result_later', 'result_request')


class ToolItem(models.Model):
    _name = 'fix.tool.item'
    _description = 'Tools checklist item'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class ToolCheck(models.Model):
    _name = 'fix.tool.check'
    _description = "Technician's tool check"
    _order = 'id desc'

    name = fields.Char(compute='_compute_name')
    technician_id = fields.Many2one('hr.employee', 'Technician', required=True, index=True, readonly=True)
    kind = fields.Selection(KINDS, required=True, readonly=True)
    day = fields.Date(required=True, index=True, readonly=True)
    # leaving the house: that visit; leaving the office: the visit whose "Start trip" asked for it
    visit_id = fields.Many2one('fix.service.visit', 'Visit', ondelete='set null', index=True, readonly=True)
    customer_name = fields.Char('Customer', related='visit_id.customer_name')
    state = fields.Selection(CHECK_STATES, default='todo', required=True, readonly=True, index=True)
    line_ids = fields.One2many('fix.tool.check.line', 'check_id', string='Tools')
    photo = fields.Image('Bag photo', max_width=1920, max_height=1920, readonly=True)
    done_on = fields.Datetime('Checked on', readonly=True)
    done_by_id = fields.Many2one('res.users', 'Checked by', readonly=True)
    missing_count = fields.Integer('Missing', compute='_compute_missing', store=True)
    missing_text = fields.Char('Missing tools', compute='_compute_missing', store=True)
    skip_reason = fields.Char('Skipped because')
    skipped_by_id = fields.Many2one('res.users', 'Skipped by', readonly=True)

    @api.depends('kind', 'technician_id', 'day')
    def _compute_name(self):
        kinds = dict(KINDS)
        for check in self:
            check.name = '%s · %s · %s' % (_(kinds.get(check.kind, '')), check.technician_id.name or '',
                                           check.day.strftime('%d %b') if check.day else '')

    @api.depends('line_ids.state')
    def _compute_missing(self):
        for check in self:
            missing = check.line_ids.filtered(lambda l: l.state == 'missing')
            check.missing_count = len(missing)
            check.missing_text = ', '.join(missing.mapped('name')) or False

    # ------------------------------------------------------------------ the list
    def _prepare(self):
        """One line per tool in the list, so a tool added later is asked too."""
        tools = self.env['fix.tool.item'].sudo().search([])
        for check in self.sudo().filtered(lambda c: c.state == 'todo'):
            new = tools - check.line_ids.tool_id
            if new:
                self.env['fix.tool.check.line'].sudo().create(
                    [{'check_id': check.id, 'tool_id': tool.id} for tool in new])

    def _lines(self):
        return self.sudo().line_ids.filtered(lambda l: l.tool_id.active).sorted(lambda l: (l.sequence, l.id))

    def _missing(self):
        """What is still to do, in words: [] when the check can be closed."""
        self.ensure_one()
        words = []
        todo = self._lines().filtered(lambda l: l.state == 'todo')
        if todo:
            words.append(_("Mark %s", ', '.join(todo.mapped('name'))))
        if not self.sudo().photo:
            words.append(_("Bag photo"))
        return words

    def _view(self, visit):
        """The check as the technician's page and My Visits draw it."""
        self.ensure_one()
        check = self.sudo()
        other = check.visit_id if check.kind == 'house' and check.visit_id != visit else check.visit_id.browse()
        return {
            'kind': check.kind,
            'title': _("Leaving the office") if check.kind == 'office' else _("Before you leave"),
            'for_ref': other.name or '',
            'for_customer': (other.customer_name or other.order_id.customer_name or '') if other else '',
            'lines': [{'id': l.id, 'name': l.name, 'state': l.state, 'note': l.note or ''} for l in check._lines()],
            'photo': bool(check.photo),
            'missing': check._missing(),
            'done': check.state != 'todo',
        }

    # ------------------------------------------------------------------ the technician's changes
    def _require_todo(self):
        if self.state != 'todo':
            raise UserError(_("This tool check is already closed."))

    def _mark(self, line_id, state, note=None):
        self._require_todo()
        line = self.sudo().line_ids.filtered(lambda l: l.id == line_id)
        if not line:
            raise UserError(_("Unknown tool."))
        if state not in dict(LINE_STATES):
            raise UserError(_("Choose in the bag or missing."))
        vals = {'state': state}
        if note is not None:
            vals['note'] = (note or '').strip()[:200] or False
        line.write(vals)

    def _set_photo(self, data):
        self._require_todo()
        try:
            raw = base64.b64decode(data or '', validate=True)
        except (ValueError, TypeError):
            raise UserError(_("The file could not be read."))
        if _sniff(raw) != 'image':
            raise UserError(_("That is not a photo."))
        if len(raw) > PHOTO_BYTES:
            raise UserError(_("The photo is too large."))
        self.sudo().photo = base64.b64encode(raw)       # a retake replaces the photo

    def _finish(self):
        """Close the check once every tool is marked and the bag photo is taken."""
        self.ensure_one()
        self._require_todo()
        missing = self._missing()
        if missing:
            raise UserError(_("Not yet - still to do: %s", ', '.join(missing)))
        check = self.sudo()
        check.write({'state': 'done', 'done_on': fields.Datetime.now(), 'done_by_id': self.env.uid})
        check._close()
        return True

    def _close(self):
        """After a check is done or skipped: the visit's check is no longer due, tools back in the
        bag close their open "missing", and a newly missing tool goes to the visit's notes."""
        Line = self.env['fix.tool.check.line'].sudo()
        for check in self.sudo():
            if check.kind == 'house' and check.visit_id.tool_house_check_id == check:
                check.visit_id.tool_house_due = False
            earlier = Line.search([('technician_id', '=', check.technician_id.id), ('is_open', '=', True),
                                   ('check_id', '!=', check.id)])
            back = check.line_ids.filtered(lambda l: l.state == 'ok').tool_id
            earlier.filtered(lambda l: l.tool_id in back).write({
                'found': True, 'found_note': _("In the bag again (%s)", check.name)})
            known = earlier.filtered(lambda l: l.tool_id not in back).tool_id
            missing = check.line_ids.filtered(lambda l: l.state == 'missing')
            # a tool already missing since an earlier check stays on that one (where it went missing)
            missing.filtered(lambda l: l.tool_id in known).write({'known': True})
            new = missing.filtered(lambda l: l.tool_id not in known)
            if new and check.visit_id:
                where = (_("leaving the office") if check.kind == 'office'
                         else _("leaving %s", check.visit_id.customer_name or check.visit_id.name))
                check.visit_id.message_post(
                    body=_("Tool missing (%(where)s): %(tools)s.", where=where,
                           tools=', '.join('%s%s' % (l.name, ' - %s' % l.note if l.note else '') for l in new)),
                    subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------ the office
    def action_skip(self):
        """A manager closes the check without it (the technician cannot do it); the reason is kept."""
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_manager'):
            raise AccessError(_("Only a manager can skip a tool check."))
        for check in self:
            check._require_todo()
            reason = (check.skip_reason or '').strip()
            if not reason:
                raise UserError(_("Write why the tool check is skipped."))
            check.sudo().write({'state': 'skipped', 'skipped_by_id': self.env.uid, 'done_on': fields.Datetime.now()})
            if check.visit_id:
                check.visit_id.message_post(body=_("%(who)s skipped the tool check (%(kind)s): %(reason)s",
                                                   who=self.env.user.name, kind=_(dict(KINDS)[check.kind]),
                                                   reason=reason), subtype_xmlid='mail.mt_note')
            check._close()
        return True


class ToolCheckLine(models.Model):
    _name = 'fix.tool.check.line'
    _description = "Tool check: one tool"
    _order = 'sequence, id'

    check_id = fields.Many2one('fix.tool.check', required=True, ondelete='cascade', index=True)
    tool_id = fields.Many2one('fix.tool.item', 'Tool', required=True, ondelete='restrict')
    name = fields.Char(related='tool_id.name')
    sequence = fields.Integer(related='tool_id.sequence', store=True)
    state = fields.Selection(LINE_STATES, default='todo', required=True)
    note = fields.Char('What happened')
    technician_id = fields.Many2one(related='check_id.technician_id', store=True, index=True)
    visit_id = fields.Many2one(related='check_id.visit_id', store=True)
    kind = fields.Selection(related='check_id.kind', store=True)
    day = fields.Date(related='check_id.day', store=True)
    where = fields.Char('Last seen', compute='_compute_where')
    # missing since an earlier check: that one carries it
    known = fields.Boolean(readonly=True)
    found = fields.Boolean()
    found_on = fields.Datetime(readonly=True)
    found_by_id = fields.Many2one('res.users', 'Found by', readonly=True)
    found_note = fields.Char('How it was found')
    is_open = fields.Boolean('Still missing', compute='_compute_is_open', store=True, index=True)

    @api.depends('state', 'found', 'known', 'check_id.state')
    def _compute_is_open(self):
        for line in self:
            line.is_open = (line.state == 'missing' and not line.found and not line.known
                            and line.check_id.state == 'done')

    @api.depends('kind', 'visit_id')
    def _compute_where(self):
        for line in self:
            if line.kind == 'office':
                line.where = _("Leaving the office")
            else:
                visit = line.visit_id
                line.where = _("At %(customer)s (%(visit)s)", customer=visit.customer_name or '?', visit=visit.name) \
                    if visit else _("At a customer")

    def write(self, vals):
        if 'found' in vals:
            vals = dict(vals, found_on=fields.Datetime.now() if vals['found'] else False,
                        found_by_id=self.env.uid if vals['found'] else False)
        return super().write(vals)

    def action_found(self):
        """The office: the tool is back."""
        self.write({'found': True})
        for line in self.filtered('visit_id'):
            line.visit_id.message_post(body=_("Tool found: %(tool)s (marked by %(who)s).",
                                              tool=line.name, who=self.env.user.name), subtype_xmlid='mail.mt_note')
        return True


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    # set when work starts at the house: "Before you leave" is then due until it is done
    tool_house_due = fields.Boolean('Tool check due', readonly=True, copy=False, index=True)
    tool_house_check_id = fields.Many2one('fix.tool.check', 'Tool check (leaving the house)',
                                          readonly=True, copy=False)

    def write(self, vals):
        if vals.get('state') == 'in_progress' and 'tool_house_due' not in vals:
            starting = self.filtered(lambda v: v.state != 'in_progress' and not v.tool_house_check_id)
            if starting and starting._vt_on():
                super(ServiceVisit, starting).write(dict(vals, tool_house_due=True))
                rest = self - starting
                return super(ServiceVisit, rest).write(vals) if rest else True
        return super().write(vals)

    # ------------------------------------------------------------------ which check
    def _vt_on(self):
        return bool(self.env['fix.tool.item'].sudo().search_count([], limit=1))

    def _vt_today(self, timestamp=None):
        """Today (or the day of `timestamp`) where the technician is (their user's time zone,
        else the company's)."""
        self.ensure_one()
        tz = (self.env.context.get('tz') or self.technician_id.user_id.tz or self.env.user.tz
              or self.company_id.partner_id.tz)
        return fields.Date.context_today(self.with_context(tz=tz) if tz else self, timestamp=timestamp)

    def _vt_office_check(self, create=True):
        """Today's "leaving the office" check of this visit's technician (done or not)."""
        self.ensure_one()
        visit = self.sudo()
        Check = self.env['fix.tool.check'].sudo()
        day = visit._vt_today()
        check = Check.search([('technician_id', '=', visit.technician_id.id), ('kind', '=', 'office'),
                              ('day', '=', day)], order='id desc', limit=1)
        if not check and create:
            check = Check.create({'technician_id': visit.technician_id.id, 'kind': 'office', 'day': day,
                                  'visit_id': visit.id})
        return check

    def _vt_house_check(self):
        self.ensure_one()
        visit = self.sudo()
        if not visit.tool_house_check_id:
            visit.tool_house_check_id = self.env['fix.tool.check'].sudo().create({
                'technician_id': visit.technician_id.id, 'kind': 'house', 'day': visit._vt_today(),
                'visit_id': visit.id})
        return visit.tool_house_check_id

    def _vt_due(self):
        """(check, required): the tool check this visit's page shows now. Required: "Start trip"
        (assigned) or the closing steps (working) wait for it."""
        self.ensure_one()
        visit = self.sudo()
        none = (self.env['fix.tool.check'], False)
        if not visit.technician_id or not visit._vt_on():
            return none
        if visit.state == 'assigned':
            # first the house the technician left without checking, then today's office check
            earlier = self.sudo().search([('technician_id', '=', visit.technician_id.id), ('tool_house_due', '=', True),
                                          ('id', '!=', visit.id)], order='id', limit=1)
            if earlier:
                check = earlier._vt_house_check()
            else:
                check = visit._vt_office_check()
                if check.state != 'todo':
                    return none
        elif visit.tool_house_due and visit.state in ('in_progress', 'done', 'cancelled'):
            # while working, "Before you leave" opens once "Can it be fixed?" is answered
            if visit.state == 'in_progress' and not (visit.check_outcome or visit.check_result or visit.close_stage):
                return none
            check = visit._vt_house_check()
        else:
            return none
        check._prepare()
        return check, visit.state in ('assigned', 'in_progress')

    def _vt_open_missing(self):
        """The technician's tools still missing, with where they were last seen."""
        self.ensure_one()
        tech = self.sudo().technician_id
        if not tech:
            return []
        lines = self.env['fix.tool.check.line'].sudo().search(
            [('technician_id', '=', tech.id), ('is_open', '=', True)], order='id desc', limit=20)
        return [{'id': l.id, 'name': l.name, 'where': l.where, 'day': fields.Date.to_string(l.day), 'note': l.note or ''}
                for l in lines]

    def _vt_lost_here(self):
        """The tools marked missing at this visit (its "Before you leave", or the office check made
        at its Start trip) and not found yet, in words ('' when none): the desk's red chip."""
        self.ensure_one()
        lines = self.env['fix.tool.check.line'].sudo().search([('visit_id', '=', self.id), ('is_open', '=', True)])
        return ', '.join(lines.mapped('name'))

    def _vt_desk(self):
        """The Booking Desk's "Tool bag": the bag the technician set off with (`start`: the office
        check on the day's first trip, else the last customer's place they left) and the bag when
        they left this customer's place (`house`). None before a technician is assigned."""
        self.ensure_one()
        visit = self.sudo()
        if not visit.technician_id or visit.state == 'draft' or not (visit._vt_on() or visit.tool_house_check_id):
            return None
        day = visit._vt_today(visit.departed_on) if visit.departed_on else visit._vt_today()
        # the technician's last finished check that day before this trip set off (office or another house)
        domain = [('technician_id', '=', visit.technician_id.id), ('day', '=', day),
                  ('state', 'in', ('done', 'skipped')), ('id', '!=', visit.tool_house_check_id.id)]
        if visit.departed_on:
            domain.append(('done_on', '<=', visit.departed_on))
        start = self.env['fix.tool.check'].sudo().search(domain, order='done_on desc, id desc', limit=1)

        def row(check):
            if not check:
                return None
            place = check.visit_id if check.kind == 'house' else check.visit_id.browse()
            return {
                'id': check.id,
                'kind': check.kind,
                'state': check.state,
                'state_label': dict(CHECK_STATES)[check.state],
                'on': fields.Datetime.to_string(check.done_on) if check.done_on else False,
                'by': (check.skipped_by_id or check.done_by_id).name or '',
                'skip_reason': check.skip_reason or '',
                'photo': bool(check.photo),
                'missing': check.missing_count,
                'customer': (place.customer_name or place.order_id.customer_name or '') if place else '',
                'ref': place.name or '',
                'tools': [{'id': l.id, 'name': l.name, 'state': l.state, 'note': l.note or '', 'found': l.found}
                          for l in check._lines()],
            }
        return {'start': row(start), 'house': row(visit.tool_house_check_id), 'house_due': visit.tool_house_due,
                'day': fields.Date.to_string(day)}

    # ------------------------------------------------------------------ the technician's steps
    def _vt_closing(self, action, args):
        """Whether this step of the technician ends the visit at the door."""
        visit = self.sudo()
        if action in CLOSING:
            return True
        if action == 'result_fixed':
            return True                         # the work is over: tools back in the bag before Finish
        if action == 'result_outcome':
            outcome = args.get('outcome')
            # no fault / not worth with the visit fee (Repair Settings' switch) goes to Finish first, when
            # there is a booking to pay
            fee = (args.get('fee') or visit._vr_fee_view()) and not (outcome == 'not_worth' and args.get('waive'))
            return outcome in NO_REPAIR and not (outcome in FEE_OUTCOMES and fee and visit.order_id)
        if action == 'result_approved_here':
            # the customer said yes: "keeps it" and "we come back" close the visit at once
            return visit.check_outcome != 'lab' and visit.pend_plan in ('keep', 'come_back')
        return False

    def _vt_tech_act(self, action, args):
        check, _required = self._vt_due()
        if not check or check.state != 'todo':
            raise UserError(_("No tool check to do now."))
        if action == 'tool_mark':
            check._mark(int(args.get('line_id') or 0), args.get('mark'), note=args.get('note'))
        elif action == 'tool_photo':
            check._set_photo(args.get('data'))
        elif action == 'tool_done':
            check._finish()
        else:
            raise UserError(_("Unknown action."))

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
        if not view.get('ref'):
            return view
        check, required = self._vt_due()
        if check:
            view['tools'] = dict(check._view(self), required=required)
        view['tools_missing'] = self._vt_open_missing()
        return view

    def _fs_tech_do(self, action='', **args):
        """Adds the tool checks (tool_* steps) to the technician's steps: "Start trip" waits for
        the office check (or an unchecked earlier house), the closing steps for "Before you leave"."""
        visit = self.sudo()
        if action.startswith('tool_'):
            try:
                with self.env.cr.savepoint():
                    visit._vt_tech_act(action, args)
            except (UserError, ValidationError) as err:
                return dict(visit._fs_tech_view(), ok=False, error='tools', message=str(err))
            return visit._fs_tech_view()
        if (action == 'on_the_way' and visit.state == 'assigned') or \
                (visit.state == 'in_progress' and visit._vt_closing(action, args)):
            check, required = visit._vt_due()
            if check and required and check.state == 'todo':
                what = _("leaving the office") if check.kind == 'office' else (
                    _("Before you leave") if check.visit_id == visit
                    else _("the house you left: %s", check.visit_id.customer_name or check.visit_id.name))
                return dict(visit._fs_tech_view(), ok=False, error='tools',
                            message=_("Check your tools first (%(what)s): %(todo)s",
                                      what=what, todo=', '.join(check._missing()) or _("tap Done")))
        return super()._fs_tech_do(action, **args)
