# -*- coding: utf-8 -*-
"""Spin & Win, the real thing behind the website's wheel.

The wheel on the site is only the picture: Odoo picks the prize. A customer spins once in
``wheel_every_days`` (their signed-in account, or the same phone number), the prize is drawn by
each prize's chance (%) and monthly limit, and the win is saved on the customer's contact with
its own code (SPIN-DIAG-7K3Q), valid ``wheel_valid_days``.

Claiming: the win goes on the customer's next booking by itself (spin_booking.py puts the prize
on the job card as a free line), and the technician marks it given at the visit (spin_visit.py).
Everything stops when the website's "Spin & Win" switch is off: no spins, nothing applied; the
wins already saved are kept for when it is on again.

The website server calls ``website_spin``, ``website_current`` and ``website_coupon`` through
the same door as bookings (the bot user's key; the phone and the customer come from the
customer's verified sign-in, never typed on the page).
"""
import random
from datetime import timedelta

from odoo import _, api, fields, models

from ...customer.models.online_order import clip, digits_of

# no 0/O, 1/I/L: read out loud at the door, typed from a WhatsApp message
CODE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_TAIL = 4
MAX_SPINS_PER_IP_HOUR = 10
STATES = [('won', 'Won'), ('used', 'On a booking'), ('given', 'Given'), ('expired', 'Expired')]


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class FixSpinWin(models.Model):
    _name = 'fix.spin.win'
    _description = 'Spin & Win prize'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _rec_name = 'code'

    site_id = fields.Many2one('online.service.site', string='Website', required=True, index=True, ondelete='restrict')
    company_id = fields.Many2one(related='site_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True, ondelete='restrict')
    phone = fields.Char(readonly=True)
    phone_digits = fields.Char(compute='_compute_phone_digits', store=True, index=True)
    item_id = fields.Many2one('fix.site.item', string='Prize', ondelete='set null', domain=[('kind', '=', 'wheel')])
    prize = fields.Char(string='Prize won', readonly=True, help='The prize as it read when it was won.')
    code = fields.Char(required=True, readonly=True, index=True, copy=False)
    won_on = fields.Datetime(readonly=True, default=fields.Datetime.now)
    valid_until = fields.Date(readonly=True)
    order_id = fields.Many2one('online.service.order', string='Booking', readonly=True, copy=False, ondelete='set null')
    used_on = fields.Datetime('Used on', readonly=True, copy=False)
    given_on = fields.Datetime('Given on', readonly=True, copy=False)
    given_by_id = fields.Many2one('res.users', 'Given by', readonly=True, copy=False)
    ip = fields.Char('IP address', readonly=True)
    state = fields.Selection(STATES, compute='_compute_state', search='_search_state')

    _code_unique = models.Constraint('unique(code)', 'Each prize code is used once.')

    @api.depends('phone')
    def _compute_phone_digits(self):
        for win in self:
            win.phone_digits = digits_of(win.phone)

    @api.depends('used_on', 'given_on', 'valid_until')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for win in self:
            if win.given_on:
                win.state = 'given'
            elif win.used_on:
                win.state = 'used'
            elif win.valid_until and win.valid_until < today:
                win.state = 'expired'
            else:
                win.state = 'won'

    def _search_state(self, operator, value):
        today = fields.Date.context_today(self)
        wanted = {value} if isinstance(value, str) else set(value or [])
        if operator in ('!=', 'not in'):
            wanted = {k for k, _label in STATES} - wanted
        parts = []
        if 'given' in wanted:
            parts.append([('given_on', '!=', False)])
        if 'used' in wanted:
            parts.append([('given_on', '=', False), ('used_on', '!=', False)])
        if 'expired' in wanted:
            parts.append([('given_on', '=', False), ('used_on', '=', False), ('valid_until', '<', today)])
        if 'won' in wanted:
            parts.append([('given_on', '=', False), ('used_on', '=', False),
                          '|', ('valid_until', '=', False), ('valid_until', '>=', today)])
        if not parts:
            return [('id', '=', False)]
        domain = []
        for part in parts[:-1]:
            domain.append('|')
        for part in parts:
            domain.extend(part)
        return domain

    # ------------------------------------------------------------------
    # The draw
    # ------------------------------------------------------------------
    @api.model
    def _roll(self, total):
        """A random point in [0, total): patched by the tests to pick a slice on purpose."""
        return random.SystemRandom().uniform(0, total)

    @api.model
    def _month_start(self):
        return fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @api.model
    def _pick(self, site):
        """The prize for a new spin: by each active prize's chance, leaving out the ones at
        their monthly limit. Empty when nothing can be won (the site shows "paused")."""
        Win = self.sudo()
        month = Win._month_start()
        pool = []
        for item in site._fix_items('wheel').filtered(lambda i: i.chance > 0):
            if item.month_limit and Win.search_count([('item_id', '=', item.id), ('won_on', '>=', month)]) >= item.month_limit:
                continue
            pool.append((item, item.chance))
        total = sum(weight for _item, weight in pool)
        if not total:
            return self.env['fix.site.item']
        roll = Win._roll(total)
        for item, weight in pool:
            roll -= weight
            if roll < 0:
                return item
        return pool[-1][0]

    @api.model
    def _new_code(self, item):
        prefix = (item.code or '').strip().upper()[:12] or 'SPIN'
        rng = random.SystemRandom()
        for _try in range(50):
            code = '%s-%s' % (prefix, ''.join(rng.choice(CODE_CHARS) for _i in range(CODE_TAIL)))
            if not self.sudo().search_count([('code', '=', code)]):
                return code
        return '%s-%s' % (prefix, ''.join(rng.choice(CODE_CHARS) for _i in range(CODE_TAIL * 2)))

    @api.model
    def _current(self, site, partner, digits):
        """The customer's win of the last ``wheel_every_days`` (their account, or the same
        number on another account), newest first; empty when they may spin."""
        since = fields.Datetime.now() - timedelta(days=max(site.wheel_every_days or 0, 1))
        domain = [('site_id', '=', site.id), ('won_on', '>=', since)]
        who = [('partner_id', '=', partner.id)]
        tail = (digits or '')[-8:]
        if len(tail) == 8:
            who = ['|'] + who + [('phone_digits', '=like', '%' + tail)]
        return self.sudo().search(domain + who, order='id desc', limit=1)

    def _website_row(self):
        self.ensure_one()
        return {
            'id': self.id, 'item_id': self.item_id.id or 0, 'prize': self.prize or '', 'code': self.code,
            'valid_until': fields.Date.to_string(self.valid_until) if self.valid_until else '',
            'state': self.state, 'order': self.order_id.name or '',
        }

    # ------------------------------------------------------------------
    # The website door
    # ------------------------------------------------------------------
    @api.model
    def _website_site(self, payload):
        self.env['online.service.order']._check_website_caller()
        p = payload if isinstance(payload, dict) else {}
        site = self.env['online.service.site']._for_host(p.get('host'))
        if not site:
            return p, site, {'ok': False, 'error': 'unknown website'}
        if not site.wheel_show:
            return p, site, {'ok': False, 'error': 'off'}
        return p, site, None

    @api.model
    def _website_partner(self, payload):
        partner = self.env['res.partner'].sudo().browse(_int(payload.get('partner_id'))).exists()
        if not partner:
            return partner, '', {'ok': False, 'error': 'sign in'}
        phone = clip(payload.get('phone') or partner.phone, 30)
        digits = digits_of(phone)
        if not 7 <= len(digits) <= 15:
            return partner, phone, {'ok': False, 'error': 'bad phone'}
        return partner, phone, None

    @api.model
    def website_spin(self, payload):
        """One spin for the signed-in customer: {'ok', 'win', 'again'?} - ``again`` when the
        customer spun already in the last ``wheel_every_days`` (the same win comes back, no new
        spin). Errors: off, sign in, bad phone, too many, paused."""
        p, site, error = self._website_site(payload)
        if error:
            return error
        partner, phone, error = self._website_partner(p)
        if error:
            return error
        Win = self.sudo()
        digits = digits_of(phone)
        current = Win._current(site, partner, digits)
        if current:
            return {'ok': True, 'win': current._website_row(), 'again': True}
        ip = clip(p.get('ip'), 64)
        if ip and Win.search_count([('ip', '=', ip), ('won_on', '>=', fields.Datetime.now() - timedelta(hours=1))]) \
                >= MAX_SPINS_PER_IP_HOUR:
            return {'ok': False, 'error': 'too many'}
        item = Win._pick(site)
        if not item:
            return {'ok': False, 'error': 'paused'}
        days = item.valid_days or site.wheel_valid_days or 14
        win = Win.create({
            'site_id': site.id, 'partner_id': partner.id, 'phone': phone, 'item_id': item.id,
            'prize': item.text or ' '.join(x for x in (item.name2, item.name) if x), 'code': Win._new_code(item),
            'valid_until': fields.Date.add(fields.Date.context_today(self), days=days), 'ip': ip,
        })
        win.message_post(body=_("Won on the website by %s.", partner.name), subtype_xmlid='mail.mt_note')
        return {'ok': True, 'win': win._website_row()}

    @api.model
    def website_current(self, payload):
        """The signed-in customer's latest win, if any: what the wheel shows when it opens
        again, and what the cart offers to add to the booking. {'ok', 'win': row | None}."""
        p, site, error = self._website_site(payload)
        if error:
            return error
        partner, phone, error = self._website_partner(p)
        if error:
            return error
        current = self.sudo()._current(site, partner, digits_of(phone))
        return {'ok': True, 'win': current._website_row() if current else None}

    @api.model
    def website_coupon(self, payload):
        """A code typed in the coupon box. {'ok', 'known', 'valid', 'prize', 'valid_until',
        'reason'}: ``known`` False for a code that is not a spin prize (the shop's own codes
        go on as plain text, as before)."""
        p, site, error = self._website_site(payload)
        if error:
            return error
        code = clip(p.get('code'), 30).upper()
        win = self.sudo().search([('site_id', '=', site.id), ('code', '=', code)], limit=1) if code else self.browse()
        if not win:
            return {'ok': True, 'known': False}
        reason = win._refusal(self.env['res.partner'].sudo().browse(_int(p.get('partner_id'))).exists())
        return {'ok': True, 'known': True, 'valid': not reason, 'reason': reason, 'prize': win.prize or '',
                'valid_until': fields.Date.to_string(win.valid_until) if win.valid_until else '', 'win_id': win.id}

    # ------------------------------------------------------------------
    # Claiming
    # ------------------------------------------------------------------
    def _refusal(self, partner):
        """Why this win cannot go on a booking by ``partner`` now; '' when it can."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.used_on:
            return _("already used on %s", self.order_id.name or _("another booking"))
        if self.valid_until and self.valid_until < today:
            return _("expired on %s", fields.Date.to_string(self.valid_until))
        if not partner:
            return _("sign in with the number that won")
        mine = (partner, partner.commercial_partner_id)
        if self.partner_id not in mine and self.partner_id.commercial_partner_id not in mine:
            return _("won by another customer")
        return ''

    def _claim(self, order, partner):
        """Put this win on ``order``: used now, the booking linked. Returns the reason when it
        cannot (nothing changes then)."""
        self.ensure_one()
        reason = self._refusal(partner)
        if reason:
            return reason
        self.sudo().write({'used_on': fields.Datetime.now(), 'order_id': order.id})
        self.message_post(body=_("Used on booking %s.", order.name), subtype_xmlid='mail.mt_note')
        return ''

    def action_mark_given(self, visit=None):
        """The customer got the prize (the technician at the door, or the office)."""
        now = fields.Datetime.now()
        for win in self.sudo().filtered(lambda w: not w.given_on):
            win.write({'given_on': now, 'given_by_id': self.env.uid})
            text = _("Prize given: %(prize)s (%(code)s), by %(who)s.", prize=win.prize, code=win.code, who=self.env.user.name)
            win.message_post(body=text, subtype_xmlid='mail.mt_note')
            if win.order_id:
                win.order_id.message_post(body=text, subtype_xmlid='mail.mt_note')
            if visit is not None:
                visit.sudo().message_post(body=text, subtype_xmlid='mail.mt_note')
        return True

    def action_open_booking(self):
        self.ensure_one()
        if not self.order_id:
            return False
        return {'type': 'ir.actions.act_window', 'res_model': 'online.service.order', 'res_id': self.order_id.id,
                'view_mode': 'form', 'target': 'current'}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    spin_win_ids = fields.One2many('fix.spin.win', 'partner_id', string='Spin & Win prizes')
    spin_win_count = fields.Integer(compute='_compute_spin_win_count')

    @api.depends('spin_win_ids')
    def _compute_spin_win_count(self):
        counts = {}
        if self.ids:
            for partner, count in self.env['fix.spin.win']._read_group(
                    [('partner_id', 'in', self.ids)], ['partner_id'], ['__count']):
                counts[partner.id] = count
        for partner in self:
            partner.spin_win_count = counts.get(partner.id, 0)

    def _spin_current_win(self):
        """The customer's prize that is still to be used (newest), for the desk."""
        self.ensure_one()
        return self.env['fix.spin.win'].sudo().search(
            [('partner_id', '=', self.id), ('state', '=', 'won')], order='id desc', limit=1)

    def action_view_spin_wins(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('369ai_fix.action_fix_spin_wins')
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id, 'search_default_filter_all': 1}
        return action
