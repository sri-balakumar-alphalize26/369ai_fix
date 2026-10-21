# -*- coding: utf-8 -*-
"""Staff review of a website booking, and what the customer answers.

Approve -> the customer gets the estimate and either a link to pick a time (all
parts in stock) or a question whether to order the missing parts. Reject (with a
reason) -> the customer is told why. The time slot and the parts answer come back
through the same signed link, via the website server (bot key).
"""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SLOT_LINK_DAYS = 7
PARTS_STATES = [
    ('none', 'No parts question'),
    ('ask', 'Asked: order the parts?'),
    ('ordering', 'Ordering parts'),
    ('ready', 'Parts ready'),
]


def _money(currency, amount):
    return '%s %.*f' % (currency.name or '', currency.decimal_places if currency else 3, amount or 0.0)


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    approved_on = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    rejected = fields.Boolean(readonly=True, copy=False, index=True)
    rejected_by_customer = fields.Boolean('Declined by customer', readonly=True, copy=False)
    reject_reason = fields.Text(readonly=True, copy=False)
    rejected_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    rejected_on = fields.Datetime(readonly=True, copy=False)
    parts_state = fields.Selection(PARTS_STATES, default='none', readonly=True, copy=False, tracking=True)
    parts_days = fields.Integer('Parts arrive in about (days)', readonly=True, copy=False)
    slot_token_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    slot_token_until = fields.Datetime(readonly=True, copy=False)
    slot_id = fields.Many2one('fix.booking.slot', string='Time slot', readonly=True, copy=False)
    slot_date = fields.Date(readonly=True, copy=False)
    slot_label = fields.Char('Booked time', compute='_compute_slot_label')
    slot_booked_on = fields.Datetime(readonly=True, copy=False)
    slot_seen_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    slot_seen_on = fields.Datetime(readonly=True, copy=False)
    call_numbers = fields.Char(compute='_compute_call_numbers')
    wb_requote_needed = fields.Boolean('Part dearer: re-price', readonly=True, copy=False)

    @api.depends('slot_id', 'slot_date')
    def _compute_slot_label(self):
        for order in self:
            order.slot_label = ('%s %s' % (order.slot_date.strftime('%a %d %b'), order.slot_id._label())
                                if order.slot_id and order.slot_date else False)

    # ------------------------------------------------------------------
    # Phone numbers: Main and Alternative from the booked address
    # ------------------------------------------------------------------
    def _wb_numbers(self):
        self.ensure_one()
        address = self.address_partner_id
        main = (address.phone if address else '') or self.phone or self.partner_id.phone or ''
        alt = getattr(address, 'mart369_alt_phone', '') if address else ''
        rows = []
        if main:
            rows.append((_('Main'), main))
        if alt and ''.join(filter(str.isdigit, alt)) != ''.join(filter(str.isdigit, main)):
            rows.append((_('Alternative'), alt))
        return rows

    @api.depends('address_partner_id', 'phone')
    def _compute_call_numbers(self):
        for order in self:
            order.call_numbers = ' · '.join('%s %s' % row for row in order._wb_numbers())

    def action_wb_call(self):
        self.ensure_one()
        numbers = self._wb_numbers()
        if not numbers:
            raise UserError(_("This booking has no phone number."))
        if len(numbers) == 1:
            return self._wb_tel(numbers[0][1])
        return {
            'type': 'ir.actions.act_window',
            'name': _("Call %s", self.customer_name or ''),
            'res_model': 'wb.call.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    @api.model
    def _wb_tel(self, number):
        tel = ''.join(ch for ch in number if ch.isdigit() or ch == '+')
        return {'type': 'ir.actions.act_url', 'url': 'tel:%s' % tel, 'target': 'self'}

    # ------------------------------------------------------------------
    # Estimate, links and messages
    # ------------------------------------------------------------------
    def _wb_estimate(self):
        """(text, total) of all job cards: repairs and parts with prices."""
        self.ensure_one()
        currency = (self.company_id or self.env.company).currency_id
        lines, total = [], 0.0
        for card in self.sudo().job_card_ids.filtered(lambda c: c.state != 'cancelled'):
            for line in card.service_line_ids:
                amount = line.unit_price * line.quantity
                total += amount
                lines.append('• %s — %s' % (line.description or line.product_id.name, _money(currency, amount)))
            for line in card.spare_part_line_ids:
                amount = line.unit_price * line.quantity
                total += amount
                lines.append('• %s — %s' % (line.description or line.product_id.name, _money(currency, amount)))
        lines.append(_("Total: %s", _money(currency, total)))
        return '\n'.join(lines), total

    def _wb_missing_parts(self):
        """Spare lines whose part is not in stock in the quantity needed."""
        self.ensure_one()
        return self.sudo().job_card_ids.filtered(lambda c: c.state != 'cancelled').spare_part_line_ids.filtered(
            lambda l: l.product_id.qty_available < (l.quantity or 1))

    def _wb_site_base(self):
        self.ensure_one()
        url = self.site_id._track_url() if self.site_id else ''
        return url[:-len('/track')] if url.endswith('/track') else url

    def _wb_new_slot_link(self):
        """A fresh signed link for this order's slot page (valid 7 days)."""
        self.ensure_one()
        token = secrets.token_urlsafe(24)
        self.sudo().write({'slot_token_hash': hashlib.sha256(token.encode()).hexdigest(),
                           'slot_token_until': fields.Datetime.now() + timedelta(days=SLOT_LINK_DAYS)})
        return '%s/slot?o=%s&t=%s' % (self._wb_site_base(), self.name, token)

    def _wb_notify(self, key, **extra):
        self.with_context(osm_extra=extra)._notify_customer(key)

    def _on_job_card_state(self, job_card_state):
        if self.env.context.get('wb_silent'):
            return None
        return super()._on_job_card_state(job_card_state)

    # ------------------------------------------------------------------
    # Approve / reject
    # ------------------------------------------------------------------
    def action_wb_approve(self):
        self.ensure_one()
        self._wb_check_open()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Approve %s", self.name),
            'res_model': 'wb.approve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_wb_reject(self):
        self.ensure_one()
        self._wb_check_open()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Reject %s", self.name),
            'res_model': 'wb.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _wb_check_open(self):
        if self.state != 'new':
            raise UserError(_("%s is already %s.", self.name,
                              dict(self._fields['state'].selection).get(self.state, self.state).lower()))

    def _wb_do_approve(self, technician=None, days=0):
        self.ensure_one()
        self._wb_check_open()
        cards = self.job_card_ids.filtered(lambda c: c.state != 'cancelled')
        if not cards.service_line_ids:
            raise UserError(_("Add the repair (with its price) to the job card before approving."))
        if technician:
            cards.sudo().write({'assigned_to': technician.id})
        missing = self._wb_missing_parts()
        self.sudo().write({
            'approved_on': fields.Datetime.now(),
            'approved_by_id': self.env.uid,
            'parts_state': 'ask' if missing else 'ready',
            'parts_days': days if missing else 0,
        })
        self.sudo()._set_state('confirmed')        # no plain "confirmed" text: ours follows
        estimate, _total = self._wb_estimate()
        link = self._wb_new_slot_link()
        if missing:
            self._wb_notify('approved_order', estimate=estimate, slot_url=link,
                            parts=', '.join(missing.mapped(lambda l: l.description or l.product_id.name)),
                            days=days or '?')
        else:
            self._wb_notify('approved', estimate=estimate, slot_url=link)
        self.message_post(body=_("Approved by %s.", self.env.user.name)
                          + (_(" Parts to order: %s.", ', '.join(missing.mapped('product_id.name'))) if missing else ''))
        self._ring()
        return True

    def _wb_do_reject(self, reason, by_customer=False):
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("Write the reason: the customer is told why."))
        order = self.sudo()
        order.write({
            'rejected': True,
            'rejected_by_customer': by_customer,
            'reject_reason': reason,
            'rejected_by_id': False if by_customer else self.env.uid,
            'rejected_on': fields.Datetime.now(),
        })
        order._set_state('cancelled')
        for card in order.job_card_ids.filtered(lambda c: c.state not in ('cancelled', 'completed')):
            card.with_context(wb_silent=True).action_cancel()
            card.message_post(body=_("Website booking %(order)s rejected: %(reason)s",
                                     order=order.name, reason=reason))
        order._wb_notify('parts_declined' if by_customer else 'rejected', reason=reason)
        order.message_post(body=(_("Customer declined: %s", reason) if by_customer
                                 else _("Rejected by %(who)s: %(reason)s", who=self.env.user.name, reason=reason)))
        order._ring()
        return True

    # ------------------------------------------------------------------
    # The customer's link: slots and the parts question (website server, bot key)
    # ------------------------------------------------------------------
    @api.model
    def _wb_from_link(self, host, ref, token):
        site = self.env['online.service.site']._for_host(host)
        order = self.sudo().search([('name', '=', (ref or '')[:30]), ('site_id', '=', site.id)],
                                   limit=1) if site else self.sudo().browse()
        if not order or not token or not order.slot_token_hash:
            return order.browse(), 'unknown'
        if not hmac.compare_digest(order.slot_token_hash, hashlib.sha256(str(token).encode()).hexdigest()):
            return order.browse(), 'unknown'
        if not order.slot_token_until or order.slot_token_until < fields.Datetime.now():
            return order.browse(), 'expired'
        if order.state == 'cancelled':
            return order.browse(), 'cancelled'
        return order, ''

    def _wb_page_state(self):
        self.ensure_one()
        if self.slot_id and self.slot_date:
            return 'booked'
        return {'ask': 'ask_parts', 'ordering': 'waiting_parts', 'ready': 'pick'}.get(self.parts_state, 'pick')

    @api.model
    def slot_options(self, host, ref, token):
        """What the slot page shows: the estimate, the state, and the free windows."""
        self._check_website_caller()
        order, error = self._wb_from_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        estimate, total = order._wb_estimate()
        company = order.company_id or self.env.company
        page = order._wb_page_state()
        days = []
        if page in ('pick', 'booked'):
            Slot = self.env['fix.booking.slot']
            for day, slots in Slot._days(company, order.mode, first_day=order._wb_first_slot_day()):
                windows = []
                for slot in slots:
                    free = slot.capacity - slot._booked(day)
                    mine = slot == order.slot_id and day == order.slot_date
                    windows.append({'slot_id': slot.id, 'label': slot._label(),
                                    'free': max(free, 0) + (1 if mine else 0), 'mine': mine})
                days.append({'date': fields.Date.to_string(day), 'label': day.strftime('%a %d %b'),
                             'windows': windows})
        return {
            'ok': True,
            'ref': order.name,
            'customer': order.customer_name or '',
            'mode': order.mode,
            'state': page,
            'estimate': estimate.split('\n'),
            'total': total,
            'currency': company.currency_id.name,
            'parts': [l.description or l.product_id.name for l in order._wb_missing_parts()],
            'parts_days': order.parts_days,
            'booked': ({'date': fields.Date.to_string(order.slot_date), 'label': order.slot_label}
                       if page == 'booked' else None),
            'can_change': page == 'booked' and order._wb_can_change_slot(),
            'days': days,
        }

    def _wb_first_slot_day(self):
        """Slots start the day after the last ordered part arrived."""
        self.ensure_one()
        requests = self.env['spare.part.purchase.request'].sudo().search(
            [('job_card_id', 'in', self.job_card_ids.ids), ('state', '=', 'received')])
        dates = [r.write_date.date() for r in requests if r.write_date]
        return (max(dates) + timedelta(days=1)) if dates else None

    def _wb_can_change_slot(self):
        self.ensure_one()
        if not (self.slot_id and self.slot_date):
            return True
        start, _end = self.slot_id._window(self.slot_date)
        hours = (self.company_id or self.env.company).wb_slot_change_hours or 0
        return fields.Datetime.now() + timedelta(hours=hours) < start

    @api.model
    def slot_book(self, host, ref, token, slot_id, date):
        """The customer picks a window. Re-checks capacity under a row lock, so two
        customers cannot both take the last place."""
        self._check_website_caller()
        order, error = self._wb_from_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        if order.parts_state in ('ask', 'ordering'):
            return {'ok': False, 'error': 'parts not ready'}
        if not order._wb_can_change_slot():
            return {'ok': False, 'error': 'too late to change'}
        slot = self.env['fix.booking.slot'].sudo().browse(int(slot_id or 0)).exists()
        try:
            day = fields.Date.to_date(date)
        except (TypeError, ValueError):
            day = None
        company = order.company_id or self.env.company
        allowed = dict(self.env['fix.booking.slot']._days(company, order.mode, first_day=order._wb_first_slot_day()))
        if not slot or not day or day not in allowed or slot not in allowed[day]:
            return {'ok': False, 'error': 'slot not available'}
        self.env.cr.execute('SELECT id FROM fix_booking_slot WHERE id = %s FOR UPDATE', [slot.id])
        same = slot == order.slot_id and day == order.slot_date
        if not same and slot._booked(day) >= slot.capacity:
            return {'ok': False, 'error': 'full'}
        start, end = slot._window(day)
        visit = order._fs_current_visit()
        if not visit or visit.state in ('done', 'cancelled'):
            visit = self.env['fix.service.visit'].sudo().create(order._fs_visit_vals())
        visit.write({'slot_start': start, 'slot_end': end})
        changed = bool(order.slot_id)
        order.write({'slot_id': slot.id, 'slot_date': day, 'slot_booked_on': fields.Datetime.now(),
                     'slot_seen_by_id': False, 'slot_seen_on': False})
        order._wb_accept_estimate()
        order._wb_notify('slot_booked', slot=order.slot_label)
        order.message_post(body=(_("Customer changed the time to %s.", order.slot_label) if changed
                                 else _("Customer booked %s (and accepted the estimate).", order.slot_label)))
        order._wb_auto_assign(visit, changed)
        order._ring()
        return {'ok': True, 'booked': {'date': fields.Date.to_string(day), 'label': order.slot_label}}

    def _wb_auto_assign(self, visit, changed=False):
        """The time is booked: the technician chosen at approval (on the job card) gets the
        visit at once - their link, and the customer's "your technician is ..." - with no
        second Assign on the desk. One who already has it gets the link again for a new time.
        Without a chosen technician the desk asks, as before. Never blocks the booking."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                visit = visit.sudo()
                placeholder = (self.company_id or self.env.company)._wb_unassigned_employee()
                chosen = visit.job_card_id.assigned_to
                if visit.state == 'draft' and (not visit.technician_id or visit.technician_id == placeholder) \
                        and chosen and chosen != placeholder:
                    visit.technician_id = chosen
                tech = visit.technician_id
                if visit.state == 'draft' and tech and tech != placeholder:
                    visit.action_assign()
                    self.message_post(body=_("%s has the visit (chosen at approval): the link went out "
                                             "with the time.", tech.name))
                elif changed and visit.state == 'assigned':
                    visit._fs_send_tech_link()
        except Exception:  # noqa: BLE001 - the customer's booking stands; the desk can still assign
            _logger.exception("Booking %s: giving the visit to the technician failed", self.name)

    def _wb_accept_estimate(self):
        """Picking a time (or 'yes, order it') accepts the estimate: remember the total."""
        for order in self:
            _text, total = order._wb_estimate()
            cards = order.job_card_ids.filtered(lambda c: c.state != 'cancelled')
            if 'estimate_total' in cards._fields:
                cards.sudo().filtered(lambda c: not c.estimate_accepted_on).write({
                    'estimate_total': total, 'estimate_accepted_on': fields.Datetime.now()})

    @api.model
    def parts_answer(self, host, ref, token, yes):
        """'Yes, order it' / 'No thanks' from the slot page."""
        self._check_website_caller()
        order, error = self._wb_from_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        if order.parts_state != 'ask':
            return {'ok': True, 'state': order._wb_page_state()}
        if not yes:
            order._wb_do_reject(_("Customer declined: the parts must be ordered."), by_customer=True)
            return {'ok': True, 'state': 'declined'}
        order._wb_order_parts()
        return {'ok': True, 'state': order._wb_page_state()}

    @api.model
    def quote_options(self, host, ref, token):
        """The new-price page: old estimate, new lines and total, parts to order."""
        self._check_website_caller()
        order, error = self._wb_from_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        cards = order.job_card_ids.filtered(lambda c: c.quote_state in ('waiting', 'accepted', 'declined'))
        estimate, total = order._wb_estimate()
        waiting = cards.filtered(lambda c: c.quote_state == 'waiting')
        return {
            'ok': True,
            'ref': order.name,
            'customer': order.customer_name or '',
            'state': 'waiting' if waiting else (cards[:1].quote_state or 'none'),
            'old_total': sum(cards.mapped('estimate_total')),
            'lines': estimate.split('\n'),
            'total': total,
            'currency': (order.company_id or self.env.company).currency_id.name,
            'parts': [l.description or l.product_id.name for l in waiting.spare_part_line_ids
                      if l.product_id.qty_available < (l.quantity or 1)],
            'found': (waiting or cards).issue_type_ids.mapped('name'),
            'at_office': any(cards.mapped('wb_at_office')),
        }

    @api.model
    def quote_answer(self, host, ref, token, yes):
        """Approve / Decline of a changed price."""
        self._check_website_caller()
        order, error = self._wb_from_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        waiting = order.job_card_ids.filtered(lambda c: c.quote_state == 'waiting')
        if not waiting:
            return {'ok': True, 'state': 'done'}
        for card in waiting:
            if yes:
                card._wb_quote_approved()
            else:
                card.quote_state = 'declined'
                card.message_post(body=_("Customer declined the new price."))
                card.activity_schedule('mail.mail_activity_data_todo', summary=_("Customer declined the new price"),
                                       user_id=(order.approved_by_id or self.env.user).id)
                card._wb_decline_at_office()
                card.sudo().fs_visit_ids._vr_declined()
        order._ring()
        return {'ok': True, 'state': 'accepted' if yes else 'declined'}

    def _wb_order_parts(self):
        """One Special Purchase Request per missing part, and a task for whoever orders."""
        self.ensure_one()
        order = self.sudo()
        Request = order.env['spare.part.purchase.request']
        assignee = order.env['ir.config_parameter'].get_param('mobile_repair.spare_request_assignee_id')
        # not called `user`: Odoo's _() reads a local named `user` to pick the language,
        # and None there crashed every order made with no buyer set
        buyer = order.env['res.users'].browse(int(assignee)).exists() if assignee and str(assignee).isdigit() else None
        holders = {}
        for line in order._wb_missing_parts():
            card = line.job_card_id
            # mobile_repair links a part order to its job card through a spare request
            # (as its own "Special Spare Part Request" button does).
            if card.id not in holders:
                holders[card.id] = order.env['spare.part.request'].create({'job_card_id': card.id})
            req = Request.create({
                'spare_request_id': holders[card.id].id,
                'product_name': line.product_id.display_name or line.description,
                'product_description': _("For %(card)s (website order %(order)s)", card=card.name, order=order.name),
                'quantity': line.quantity or 1,
                'estimated_cost': line.product_id.standard_price,
                'urgency': 'high',
                'company_id': card.company_id.id,
            })
            if hasattr(req, 'action_request'):
                req.action_request()
            if buyer:
                req.activity_schedule('mail.mail_activity_data_todo', user_id=buyer.id,
                                      summary=_("Order %s for a website booking", req.product_name))
        order._wb_accept_estimate()
        order.write({'parts_state': 'ordering'})
        order._wb_notify('parts_ordering', days=order.parts_days or '?')
        order.message_post(body=_("Customer said yes: order the parts."))

    # ------------------------------------------------------------------
    # Alarm 2 (slot booked) and the dashboard
    # ------------------------------------------------------------------
    def action_wb_slot_seen(self):
        self.write({'slot_seen_by_id': self.env.uid, 'slot_seen_on': fields.Datetime.now()})
        self._ring()
        return True

    @api.model
    def alarm_state(self):
        state = super().alarm_state()
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
            state['slots'] = []
            return state
        orders = self.sudo().search([('slot_booked_on', '!=', False), ('slot_seen_by_id', '=', False),
                                     ('state', '!=', 'cancelled'),
                                     ('company_id', 'in', self.env.companies.ids)], limit=20)
        state['slots'] = [{'id': o.id, 'name': o.name, 'customer': o.customer_name or o.phone or '',
                           'slot': o.slot_label or ''} for o in orders]
        return state

    @api.model
    def customer_orders(self, host, phone):
        result = super().customer_orders(host, phone)
        if not (isinstance(result, dict) and result.get('ok') and result.get('orders')):
            return result
        site = self.env['online.service.site']._for_host(host)
        orders = {o.name: o for o in self.sudo().search(
            [('site_id', '=', site.id), ('name', 'in', [r['ref'] for r in result['orders']])])}
        for row in result['orders']:
            order = orders.get(row['ref'])
            if not order:
                continue
            row['slot'] = order.slot_label or ''
            row['parts'] = {'waiting': order.parts_state in ('ask', 'ordering'),
                            'expected': order._wb_parts_expected()}
            if order.rejected:
                row['reason'] = order.reject_reason or ''
        return result

    def _wb_parts_expected(self):
        self.ensure_one()
        reqs = self.env['spare.part.purchase.request'].sudo().search(
            [('job_card_id', 'in', self.job_card_ids.ids), ('state', 'not in', ('received', 'rejected'))])
        dates = [r.expected_date for r in reqs if 'expected_date' in r._fields and r.expected_date]
        return fields.Date.to_string(max(dates)) if dates else ''


class MobileRepairDashboard(models.Model):
    _inherit = 'mobile.repair.dashboard'

    @api.model
    def get_dashboard_data(self):
        data = super().get_dashboard_data()
        try:
            Order = self.env['online.service.order']
            base = [('company_id', '=', self.env.company.id)]
            today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            data.update({
                'wb_waiting': Order.search_count(base + [('state', '=', 'new')]),
                'wb_slot_unseen': Order.search_count(base + [('slot_booked_on', '!=', False),
                                                             ('slot_seen_by_id', '=', False),
                                                             ('state', '!=', 'cancelled')]),
                'wb_parts': Order.search_count(base + [('parts_state', 'in', ('ask', 'ordering')),
                                                       ('state', '!=', 'cancelled')]),
                'wb_rejected_today': Order.search_count(base + [('rejected', '=', True),
                                                                ('rejected_on', '>=', today)]),
            })
        except Exception:  # noqa: BLE001 - the dashboard must open even if this fails
            _logger.exception("Website booking numbers for the dashboard failed")
        return data
