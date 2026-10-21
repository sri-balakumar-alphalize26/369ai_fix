# -*- coding: utf-8 -*-
"""A repair booking sent from the Danat Fix / 369 ai Fix website.

The website creates it through the external API (`website_create`). From
then on there are two ways to act on it - the Store screen and the WhatsApp
poll in the staff group - and both go through `_transition`, which locks the
row first. Whichever side is first decides; the other side is told.
"""

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

OPT_ACCEPT = '✅ Accept'
OPT_CALL = '📞 Call customer first'
OPT_REJECT = '❌ Reject'
POLL_OPTIONS = [OPT_ACCEPT, OPT_CALL, OPT_REJECT]

# Which states each action may start from. Anything else is a late tap.
_FROM = {
    'accept': ('new', 'calling'),
    'call': ('new',),
    'done': ('accepted', 'calling'),
    'cancel': ('new', 'calling', 'accepted'),
    'reopen': ('cancelled', 'done'),
}
_TO = {
    'accept': 'accepted',
    'call': 'calling',
    'done': 'done',
    'cancel': 'cancelled',
    'reopen': 'new',
}

_SOURCES = [
    ('wizard', 'Booking wizard'),
    ('panel', 'Service panel'),
    ('cart', 'Cart'),
    ('services_cart', 'Services page cart'),
    ('someone_else', 'Booked for someone else'),
    ('quick', 'Quick contact'),
]
_BRANDS = [('danatfix', 'Danat Fix'), ('369', '369 ai Fix')]


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _clip(value, size):
    return str(value or '').strip()[:size]


class DanatfixBooking(models.Model):
    _name = 'danatfix.booking'
    _description = 'Website Repair Booking'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Booking', default='/', readonly=True, copy=False,
                       index=True)
    web_ref = fields.Char('Website ref', readonly=True, index=True, copy=False,
                          help="The reference the customer sees in their "
                               "WhatsApp message.")
    state = fields.Selection([
        ('new', 'New'),
        ('calling', 'Calling customer'),
        ('accepted', 'Accepted'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='new', required=True, index=True, tracking=True)

    customer_name = fields.Char('Customer', tracking=True)
    phone = fields.Char(tracking=True)
    email = fields.Char()
    area = fields.Char()
    address = fields.Char()
    map_url = fields.Char('Map link')
    brand = fields.Selection(_BRANDS, default='danatfix')
    source = fields.Selection(_SOURCES, default='wizard')
    line_ids = fields.One2many('danatfix.booking.line', 'booking_id',
                               string='Repairs')
    summary = fields.Char(compute='_compute_summary', store=True)
    coupon = fields.Char()
    note = fields.Text()
    message = fields.Text('WhatsApp text',
                          help="What the customer's WhatsApp message said.")
    page = fields.Char('Website page')
    ip = fields.Char('IP address')

    partner_id = fields.Many2one('res.partner', string='Contact',
                                 tracking=True)
    accepted_by_id = fields.Many2one('res.users', string='Taken by',
                                     tracking=True)
    accepted_by_name = fields.Char('Taken by (WhatsApp name)')
    accepted_on = fields.Datetime()
    decided_via = fields.Selection([('screen', 'Store screen'),
                                    ('whatsapp', 'WhatsApp poll')])

    poll_sent = fields.Boolean(readonly=True, copy=False)
    poll_wa_id = fields.Char('Poll message id', readonly=True, index=True,
                             copy=False)
    poll_error = fields.Char(readonly=True, copy=False)

    @api.depends('line_ids.device', 'line_ids.model', 'line_ids.issue',
                  'line_ids.qty')
    def _compute_summary(self):
        for booking in self:
            parts = []
            for line in booking.line_ids:
                label = line.issue or ''
                if line.qty and line.qty > 1:
                    label += ' ×%s' % line.qty
                what = ' '.join(p for p in (line.device, line.model) if p)
                parts.append('%s — %s' % (what, label) if what else label)
            booking.summary = '; '.join(parts)[:250]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'danatfix.booking') or '/'
        return super().create(vals_list)

    # ======================================================================
    # From the website
    # ======================================================================
    @api.model
    def website_create(self, payload):
        """Called by the website server through execute_kw.

        Everything is re-checked here: the website already validated it, but
        this is the door, and a door does not trust the hallway.
        Returns {'ok': bool, 'ref': name, 'error': str}.
        """
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(_("Only internal users can send bookings."))
        p = payload if isinstance(payload, dict) else {}

        web_ref = _clip(p.get('ref'), 20)
        if web_ref and not re.fullmatch(r'[A-Z0-9-]{4,20}', web_ref):
            web_ref = ''
        Booking = self.sudo()
        # A retried request (timeout on the website side) must not make two.
        if web_ref:
            same = Booking.search([('web_ref', '=', web_ref)], limit=1)
            if same:
                return {'ok': True, 'ref': same.name, 'duplicate': True}

        phone = _clip(p.get('phone'), 30)
        email = _clip(p.get('email'), 120)
        if not phone and not email:
            return {'ok': False, 'error': 'phone or email required'}
        digits = _digits(phone)
        if phone and not 7 <= len(digits) <= 15:
            return {'ok': False, 'error': 'bad phone'}

        # Ten bookings from one number in ten minutes is a script, not a
        # customer - and every one of them would ring the shop.
        if digits:
            recent = Booking.search_count([
                ('create_date', '>=', fields.Datetime.subtract(
                    fields.Datetime.now(), minutes=10)),
                ('phone', 'ilike', digits[-8:]),
            ])
            if recent >= 10:
                return {'ok': False, 'error': 'too many'}

        source = p.get('source') if p.get('source') in dict(_SOURCES) else 'wizard'
        brand = p.get('brand') if p.get('brand') in dict(_BRANDS) else 'danatfix'

        map_url = ''
        try:
            lat, lng = float(p.get('lat')), float(p.get('lng'))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                map_url = 'https://maps.google.com/?q=%.5f,%.5f' % (lat, lng)
        except (TypeError, ValueError):
            pass

        lines = []
        for raw in (p.get('lines') or [])[:30]:
            if not isinstance(raw, dict) or not _clip(raw.get('issue'), 120):
                continue
            try:
                qty = min(max(int(raw.get('qty') or 1), 1), 20)
            except (TypeError, ValueError):
                qty = 1
            lines.append((0, 0, {
                'device': _clip(raw.get('device'), 80),
                'model': _clip(raw.get('model'), 80),
                'issue': _clip(raw.get('issue'), 120),
                'qty': qty,
            }))

        booking = Booking.create({
            'web_ref': web_ref or False,
            'customer_name': _clip(p.get('name'), 80),
            'phone': phone,
            'email': email,
            'area': _clip(p.get('area'), 120),
            'address': _clip(p.get('address'), 200),
            'map_url': map_url,
            'brand': brand,
            'source': source,
            'coupon': _clip(p.get('coupon'), 30),
            'note': _clip(p.get('note'), 500),
            'message': _clip(p.get('message'), 2000),
            'page': _clip(p.get('page'), 200),
            'ip': _clip(p.get('ip'), 64),
            'line_ids': lines,
        })
        booking._notify_screens()
        booking._post_to_staff_group()
        return {'ok': True, 'ref': booking.name}

    # ======================================================================
    # Store screen
    # ======================================================================
    @api.model
    def alarm_state(self):
        """Small enough to poll from every page of the web client."""
        settings = self.env['danatfix.booking.settings'].get_settings()
        # technicians work from My Visits (369ai_fix) and cannot open the desk: no alarm
        user = self.env.user
        tech_only = (user.has_group('mobile_repair.group_mobile_repair_technician')
                     and not user.has_group('mobile_repair.group_mobile_repair_receptionist'))
        hears = not tech_only and (not settings.alarm_user_ids or user in settings.alarm_user_ids)
        return {
            'new': self.sudo().search_count([('state', '=', 'new')]) if hears else 0,
            'ring': max(3, settings.ring_seconds or 20),
            'repeat': max(3, settings.repeat_seconds or 15),
        }

    @api.model
    def screen_data(self):
        """Everything still open, oldest first: the one waiting longest is
        the one to deal with."""
        settings = self.env['danatfix.booking.settings'].get_settings()
        bookings = self.search([('state', 'in', ('new', 'calling', 'accepted'))],
                               order='id asc', limit=200)
        return {
            'rows': [b._screen_row() for b in bookings],
            'new': len(bookings.filtered(lambda b: b.state == 'new')),
            'ring': max(3, settings.ring_seconds or 20),
            'repeat': max(3, settings.repeat_seconds or 15),
            'poll_ready': bool(settings.poll_enabled and settings._group_jid()),
        }

    def _screen_row(self):
        self.ensure_one()
        brands, sources = dict(_BRANDS), dict(_SOURCES)
        return {
            'id': self.id,
            'name': self.name,
            'web_ref': self.web_ref or '',
            'state': self.state,
            'customer': self.customer_name or '',
            'phone': self.phone or '',
            'phone_digits': _digits(self.phone),
            'email': self.email or '',
            'area': self.area or '',
            'address': self.address or '',
            'map_url': self.map_url or '',
            'brand': brands.get(self.brand, ''),
            'source': sources.get(self.source, ''),
            'lines': [{'id': l.id, 'device': l.device or '', 'model': l.model or '',
                       'issue': l.issue or '', 'qty': l.qty or 1}
                      for l in self.line_ids],
            'coupon': self.coupon or '',
            'note': self.note or '',
            'created': fields.Datetime.to_string(self.create_date),
            'taken_by': self.accepted_by_id.name or self.accepted_by_name or '',
            'decided_via': self.decided_via or '',
            'poll_sent': self.poll_sent,
            'poll_error': self.poll_error or '',
        }

    def screen_act(self, action):
        """A button on the Store screen."""
        self.ensure_one()
        if action not in _FROM:
            raise UserError(_("Unknown action."))
        ok, before = self._transition(action, user=self.env.user, via='screen')
        data = self.screen_data()
        if not ok:
            self.invalidate_recordset()
            # Somebody was quicker - on another screen or on WhatsApp.
            data['warning'] = _(
                "%(ref)s is already %(state)s%(who)s.",
                ref=self.name,
                state=dict(self._fields['state'].selection).get(before, before).lower(),
                who=(_(" (taken by %s)", self.accepted_by_id.name or self.accepted_by_name)
                     if self.accepted_by_id or self.accepted_by_name else ''))
        return data

    # ======================================================================
    # One way to change state
    # ======================================================================
    def _transition(self, action, user=None, wa_name='', via='screen'):
        """(changed, state_before). Locks the row so a tap on WhatsApp and a
        click on the screen in the same second cannot both win."""
        self.ensure_one()
        # Pending ORM writes first, or the locked read below sees a state
        # from before this transaction's own last change.
        self.env['danatfix.booking'].flush_model(['state'])
        self.env.cr.execute(
            'SELECT state FROM danatfix_booking WHERE id = %s FOR UPDATE',
            [self.id])
        row = self.env.cr.fetchone()
        before = row[0] if row else self.state
        if before not in _FROM[action]:
            return False, before
        who = (user.name if user else '') or wa_name or _('someone')
        vals = {'state': _TO[action]}
        if action in ('accept', 'call'):
            vals.update({
                'accepted_by_id': user.id if user else False,
                'accepted_by_name': wa_name or (user.name if user else ''),
                'accepted_on': fields.Datetime.now(),
                'decided_via': via,
            })
        if action == 'reopen':
            vals.update({'accepted_by_id': False, 'accepted_by_name': False,
                         'accepted_on': False, 'decided_via': False})
        booking = self.sudo()
        booking.write(vals)
        if action == 'accept' and not booking.partner_id and booking.phone:
            booking.partner_id = booking._find_or_create_partner()
        booking.message_post(body=_("%(action)s by %(who)s (%(via)s).",
                                    action=dict(self._fields['state'].selection)[vals['state']],
                                    who=who,
                                    via=dict(self._fields['decided_via'].selection)[via]))
        booking._notify_screens()
        booking._tell_staff_group(action, who, via)
        return True, before

    def _find_or_create_partner(self):
        self.ensure_one()
        digits = _digits(self.phone)
        Partner = self.env['res.partner'].sudo()
        if len(digits) >= 7:
            for partner in Partner.search([('phone', 'ilike', digits[-4:])], limit=50):
                if _digits(partner.phone).endswith(digits[-8:]):
                    return partner
        return Partner.create({
            'name': self.customer_name or self.phone,
            'phone': self.phone,
            'email': self.email or False,
            'street': self.address or False,
            'city': self.area or False,
        })

    def _notify_screens(self):
        try:
            self.env['bus.bus']._sendone('danatfix_booking', 'danatfix_booking/refresh',
                                         {'ids': self.ids})
        except Exception as err:  # noqa: BLE001 - the 20 s poll catches up
            _logger.warning("Website booking: bus notify failed: %s", err)

    # ======================================================================
    # WhatsApp staff group
    # ======================================================================
    def _wa_target(self):
        settings = self.env['danatfix.booking.settings'].get_settings()
        if not settings.poll_enabled:
            return None, None
        jid = settings._group_jid()
        session = settings._session() if jid else None
        return (session, jid) if session and jid else (None, None)

    def _wa_send(self, session, jid, text):
        """Send, treating a queued message as sent. Returns an error string."""
        try:
            with self.env.cr.savepoint():
                session.send_message(jid, text)
        except Exception as err:  # noqa: BLE001
            if type(err).__name__ == 'WhatsAppQueued':
                return ''
            return str(err)[:200] or type(err).__name__
        return ''

    def _staff_text(self):
        self.ensure_one()
        brands = dict(_BRANDS)
        out = [_("📥 *New website booking %s*", self.name)]
        head = ' · '.join(p for p in (self.web_ref, brands.get(self.brand)) if p)
        if head:
            out.append(head)
        if self.customer_name:
            out.append('👤 %s' % self.customer_name)
        if self.phone:
            out.append('📞 %s' % self.phone)
        if self.email:
            out.append('✉️ %s' % self.email)
        where = ', '.join(p for p in (self.address, self.area) if p)
        if where:
            out.append('📍 %s' % where)
        if self.map_url:
            out.append(self.map_url)
        for line in self.line_ids:
            what = ' '.join(p for p in (line.device, line.model) if p)
            qty = ' ×%s' % line.qty if line.qty > 1 else ''
            out.append('🔧 %s%s%s' % ('%s — ' % what if what else '', line.issue, qty))
        if self.coupon:
            out.append(_("🏷 Coupon: %s", self.coupon))
        if self.note:
            out.append('📝 %s' % self.note)
        return '\n'.join(out)

    def _post_to_staff_group(self):
        """The booking, then the poll. Never raises: the booking is saved and
        the alarm rings whatever WhatsApp does."""
        self.ensure_one()
        session, jid = self._wa_target()
        if not session:
            return
        error = self._wa_send(session, jid, self._staff_text())
        if not error:
            try:
                with self.env.cr.savepoint():
                    session.sa_send_poll(jid, _("%s — who takes this job?", self.name),
                                         POLL_OPTIONS)
            except Exception as err:  # noqa: BLE001
                if type(err).__name__ != 'WhatsAppQueued':
                    error = str(err)[:200] or type(err).__name__
        if error:
            self.write({'poll_error': error})
            self.message_post(body=_("WhatsApp poll not sent: %s", error))
            _logger.warning("Website booking %s: WhatsApp poll not sent: %s",
                            self.name, error)
            return
        vals = {'poll_sent': True, 'poll_error': False}
        sent = self._find_poll_row(session, jid)
        if sent:
            vals['poll_wa_id'] = sent.wa_message_id
        self.write(vals)

    def _find_poll_row(self, session, jid):
        """The gateway logs what it sent, with WhatsApp's id - the id a vote
        will name. Scoped to this group, this booking's question and the
        last minute, so another poll sent in the same second is not taken."""
        self.ensure_one()
        return self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', session.id),
            ('direction', '=', 'outgoing'),
            ('phone', 'in', [jid, jid.split('@')[0]]),
            ('message', 'ilike', self.name),
            ('wa_message_id', '!=', False),
            ('create_date', '>=', fields.Datetime.subtract(
                fields.Datetime.now(), seconds=60)),
        ], order='id desc', limit=1)

    def _tell_staff_group(self, action, who, via):
        """One short line in the group, only when the group was told about
        the booking in the first place."""
        self.ensure_one()
        if not self.poll_sent:
            return
        session, jid = self._wa_target()
        if not session:
            return
        where = _(" on the Store screen") if via == 'screen' else ''
        text = {
            'accept': _("✅ %(ref)s taken by %(who)s%(where)s.%(phone)s"),
            'call': _("📞 %(who)s is calling the customer for %(ref)s%(where)s."),
            'done': _("🏁 %(ref)s done (%(who)s)."),
            'cancel': _("❌ %(ref)s cancelled by %(who)s%(where)s."),
            'reopen': _("↩️ %(ref)s reopened by %(who)s - it needs someone again."),
        }[action] % {
            'ref': self.name, 'who': who, 'where': where,
            'phone': (' %s' % self.phone) if self.phone else '',
        }
        error = self._wa_send(session, jid, text)
        if error:
            _logger.info("Website booking %s: group note not sent: %s", self.name, error)

    @api.model
    def _from_poll_ref(self, poll_ref):
        """The booking a WhatsApp vote belongs to, or empty.

        By the id stored when the poll went out; failing that (the gateway
        queued it, so the id came later) by the logged poll's own text, which
        always carries the booking number."""
        poll_ref = (poll_ref or '').strip()
        if not poll_ref:
            return self.browse()
        Booking = self.sudo()
        booking = Booking.search([('poll_wa_id', '=', poll_ref)], limit=1)
        if booking:
            return booking
        row = self.env['whatsapp.message'].sudo().search(
            [('wa_message_id', '=', poll_ref), ('direction', '=', 'outgoing')], limit=1)
        match = re.search(r'\bWB/\d+', row.message or '')
        if not match:
            return Booking.browse()
        booking = Booking.search([('name', '=', match.group(0))], limit=1)
        if booking and not booking.poll_wa_id:
            booking.poll_wa_id = poll_ref
        return booking

    def _apply_vote(self, choice, digits, push_name):
        """A tap in the staff group. The first tap decides; a changed or late
        vote is ignored without a word, because WhatsApp lets anyone change a
        vote at any time and each change arrives as a fresh message."""
        self.ensure_one()
        label = (choice or '').lower()
        action = ('accept' if 'accept' in label else
                  'call' if 'call' in label else
                  'cancel' if 'reject' in label else '')
        if not action:
            return False
        # A poll only decides an undecided booking. Once somebody has taken
        # it, a Reject tapped later (or a vote changed) must not cancel it -
        # that is a job for the screen, on purpose.
        self.env['danatfix.booking'].flush_model(['state'])
        self.invalidate_recordset(['state'])
        if self.state not in ('new', 'calling'):
            return False
        user = self._user_for_digits(digits)
        changed, _before = self._transition(
            action, user=user or None, wa_name=push_name or digits, via='whatsapp')
        return changed

    @api.model
    def _user_for_digits(self, digits):
        tail = _digits(digits)[-8:]
        Users = self.env['res.users'].sudo()
        if len(tail) < 8:
            return Users.browse()
        for user in Users.search([('share', '=', False)]):
            partner = user.partner_id
            for value in (partner.phone, getattr(partner, 'mobile', False)):
                if value and _digits(value).endswith(tail):
                    return user
        if 'hr.employee' in self.env:
            for emp in self.env['hr.employee'].sudo().search([('user_id', '!=', False)]):
                for value in (emp.mobile_phone, emp.work_phone):
                    if value and _digits(value).endswith(tail):
                        return emp.user_id
        return Users.browse()


class DanatfixBookingLine(models.Model):
    _name = 'danatfix.booking.line'
    _description = 'Website Repair Booking Line'

    booking_id = fields.Many2one('danatfix.booking', required=True,
                                 ondelete='cascade', index=True)
    device = fields.Char()
    model = fields.Char()
    issue = fields.Char('Repair', required=True)
    qty = fields.Integer(default=1)
