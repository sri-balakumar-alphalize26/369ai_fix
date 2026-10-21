# -*- coding: utf-8 -*-
"""Website repair orders.

The website server calls `website_create` through /json/2 with a dedicated
bot user's API key. Everything is re-checked here: the website validated it
already, but this is the door.
"""
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .online_message import STATUS_KEYS

_logger = logging.getLogger(__name__)

MODES = [
    ('doorstep', 'Doorstep Service'),
    ('pickup', 'Pickup & Service'),
    ('to_confirm', 'To confirm'),
]
STATES = [
    ('new', 'New'),
    ('confirmed', 'Confirmed'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
SOURCES = [
    ('wizard', 'Services page'),
    ('cart', 'Cart'),
    ('services_cart', 'Services cart'),
    ('panel', 'Service panel'),
    ('other', 'Other'),
]
# What the customer sees, in order (the "live status" timeline).
TIMELINE = [
    ('received', 'Received'),
    ('confirmed', 'Confirmed'),
    ('inspection', 'Inspection'),
    ('quotation', 'Quotation'),
    ('repair', 'Repair'),
    ('completed', 'Completed'),
]
# job.card state -> message / timeline key
JOB_CARD_KEYS = {
    'inspection': 'inspection',
    'quotation': 'quotation',
    'repair': 'repair',
    'completed': 'completed',
    'cancelled': 'cancelled',
}


def digits_of(value):
    return re.sub(r'\D', '', value or '')


def clip(value, size):
    if value is None or value is False:
        return ''
    return str(value).strip()[:size]


class OnlineServiceOrder(models.Model):
    _name = 'online.service.order'
    _description = 'Online Service Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Order', default='/', readonly=True, copy=False, index=True)
    web_ref = fields.Char('Website ref', readonly=True, copy=False, index=True,
                          help="Id made by the website; a retried request never makes a second order.")
    site_id = fields.Many2one('online.service.site', string='Website', readonly=True, index=True,
                              ondelete='restrict')
    company_id = fields.Many2one(related='site_id.company_id', store=True)
    mode = fields.Selection(MODES, string='Service type', default='to_confirm', required=True, tracking=True)
    state = fields.Selection(STATES, default='new', required=True, tracking=True, index=True)
    source = fields.Selection(SOURCES, default='wizard')

    customer_name = fields.Char('Customer', tracking=True)
    phone = fields.Char(tracking=True)
    phone_digits = fields.Char(compute='_compute_phone_digits', store=True, index=True)
    email = fields.Char()
    area = fields.Char()
    address = fields.Char()
    map_url = fields.Char('Map link')
    coupon = fields.Char()
    note = fields.Text('Customer note')
    line_ids = fields.One2many('online.service.order.line', 'order_id', string='Repairs')
    summary = fields.Char(compute='_compute_summary', store=True)

    partner_id = fields.Many2one('res.partner', string='Contact', tracking=True)
    job_card_id = fields.Many2one('job.card', string='Job Card', readonly=True, copy=False, tracking=True)
    job_card_state = fields.Selection(related='job_card_id.state', string='Job Card status')
    opened_by_id = fields.Many2one('res.users', 'Opened by', readonly=True, copy=False)
    opened_on = fields.Datetime(readonly=True, copy=False)
    confirmed_on = fields.Datetime(readonly=True, copy=False)
    done_on = fields.Datetime(readonly=True, copy=False)
    page = fields.Char('Website page', readonly=True)
    ip = fields.Char('IP address', readonly=True)

    # ------------------------------------------------------------------
    @api.depends('phone')
    def _compute_phone_digits(self):
        for order in self:
            order.phone_digits = digits_of(order.phone)

    @api.depends('line_ids.device', 'line_ids.model', 'line_ids.issue', 'line_ids.qty')
    def _compute_summary(self):
        for order in self:
            parts = []
            for line in order.line_ids:
                what = ' '.join(p for p in (line.device, line.model) if p)
                item = line.issue + (' x%d' % line.qty if line.qty > 1 else '')
                parts.append('%s (%s)' % (item, what) if what else item)
            order.summary = '; '.join(parts)[:250]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('online.service.order') or '/'
        orders = super().create(vals_list)
        for order in orders:
            order._notify_customer('received')
        orders._ring()
        return orders

    # ------------------------------------------------------------------
    # The door: called by the website server
    # ------------------------------------------------------------------
    @api.model
    def _check_website_caller(self):
        if not self.env.user._is_internal():
            raise AccessError(_("Only internal users can send website orders."))

    @api.model
    def website_create(self, payload):
        """Create one order from the website. Returns {'ok', 'ref', 'error'}."""
        self._check_website_caller()
        p = payload if isinstance(payload, dict) else {}
        site = self.env['online.service.site']._for_host(p.get('host'))
        if not site:
            return {'ok': False, 'error': 'unknown website'}
        Order = self.sudo().with_company(site.company_id)

        web_ref = clip(p.get('ref'), 24)
        if web_ref and not re.fullmatch(r'[A-Za-z0-9-]{4,24}', web_ref):
            web_ref = ''
        if web_ref:
            same = Order.search([('web_ref', '=', web_ref), ('site_id', '=', site.id)], limit=1)
            if same:
                return {'ok': True, 'ref': same.name, 'duplicate': True}

        phone = clip(p.get('phone'), 30)
        digits = digits_of(phone)
        if not 7 <= len(digits) <= 15:
            return {'ok': False, 'error': 'bad phone'}
        # Ten orders from one number in ten minutes is a script, and every
        # one of them would ring the shop.
        recent = Order.search_count([
            ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), minutes=10)),
            ('phone_digits', '=', digits),
        ])
        if recent >= 10:
            return {'ok': False, 'error': 'too many'}

        lines = []
        for raw in (p.get('lines') or [])[:30]:
            if not isinstance(raw, dict) or not clip(raw.get('issue'), 120):
                continue
            try:
                qty = min(max(int(raw.get('qty') or 1), 1), 20)
            except (TypeError, ValueError):
                qty = 1
            lines.append((0, 0, {
                'device': clip(raw.get('device'), 80),
                'model': clip(raw.get('model'), 80),
                'issue': clip(raw.get('issue'), 120),
                'qty': qty,
            }))
        if not lines:
            return {'ok': False, 'error': 'nothing booked'}

        map_url = ''
        try:
            lat, lng = float(p.get('lat')), float(p.get('lng'))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                map_url = 'https://maps.google.com/?q=%.5f,%.5f' % (lat, lng)
        except (TypeError, ValueError):
            pass

        mode = p.get('mode') if p.get('mode') in dict(MODES) else 'to_confirm'
        source = p.get('source') if p.get('source') in dict(SOURCES) else 'other'
        order = Order.create({
            'web_ref': web_ref or False,
            'site_id': site.id,
            'mode': mode,
            'source': source,
            'customer_name': clip(p.get('name'), 80),
            'phone': phone,
            'email': clip(p.get('email'), 120),
            'area': clip(p.get('area'), 120),
            'address': clip(p.get('address'), 200),
            'map_url': map_url,
            'coupon': clip(p.get('coupon'), 30),
            'note': clip(p.get('note'), 500),
            'page': clip(p.get('page'), 200),
            'ip': clip(p.get('ip'), 64),
            'line_ids': lines,
        })
        return {'ok': True, 'ref': order.name}

    # ------------------------------------------------------------------
    # Staff actions
    # ------------------------------------------------------------------
    def _set_state(self, state, notify_key=None):
        now = fields.Datetime.now()
        for order in self:
            if order.state == state:
                continue
            vals = {'state': state}
            if state == 'confirmed' and not order.confirmed_on:
                vals['confirmed_on'] = now
            if state == 'done':
                vals['done_on'] = now
            order.write(vals)
            if notify_key:
                order._notify_customer(notify_key)
        self._ring()

    def action_mark_opened(self):
        """Somebody looked at it: the alarm stops for this order."""
        for order in self.filtered(lambda o: not o.opened_by_id):
            order.sudo().write({'opened_by_id': self.env.uid, 'opened_on': fields.Datetime.now()})
        self._ring()
        return True

    def action_confirm(self):
        self.filtered(lambda o: o.state == 'new')._set_state('confirmed', 'confirmed')

    def action_done(self):
        self.filtered(lambda o: o.state in ('new', 'confirmed'))._set_state('done', 'done')

    def action_cancel(self):
        self.filtered(lambda o: o.state in ('new', 'confirmed'))._set_state('cancelled', 'cancelled')

    def action_reopen(self):
        self.filtered(lambda o: o.state in ('done', 'cancelled'))._set_state('new')

    def _find_or_create_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        Partner = self.env['res.partner'].sudo()
        partner = Partner.browse()
        # Same person = same last 8 digits, however the number was typed.
        tail = (self.phone_digits or '')[-8:]
        if len(tail) == 8:
            for cand in Partner.search([('phone', 'like', tail[-4:])], limit=300):
                if digits_of(cand.phone).endswith(tail):
                    partner = cand
                    break
        if not partner:
            partner = Partner.create({
                'name': self.customer_name or self.phone,
                'phone': self.phone,
                'email': self.email or False,
                'street': self.address or False,
                'street2': self.area or False,
            })
        self.partner_id = partner
        return partner

    def action_create_job_card(self):
        self.ensure_one()
        if self.job_card_id:
            return self.action_open_job_card()
        if self.state in ('done', 'cancelled'):
            raise UserError(_("Reopen the order first."))
        partner = self._find_or_create_partner()
        issue_lines = ['%s%s%s' % (
            line.issue,
            ' x%d' % line.qty if line.qty > 1 else '',
            ' - %s' % ' '.join(p for p in (line.device, line.model) if p) if (line.device or line.model) else '',
        ) for line in self.line_ids]
        issue = '\n'.join(issue_lines)
        if self.note:
            issue += '\n\n%s: %s' % (_("Customer note"), self.note)
        issue += '\n\n%s %s (%s)' % (_("Website order"), self.name, dict(MODES)[self.mode])
        return {
            'type': 'ir.actions.act_window',
            'name': _("New Job Card"),
            'res_model': 'job.card',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_partner_id': partner.id,
                'default_issue': issue,
                'default_delivery_type': 'door_step',
                'default_online_order_id': self.id,
            },
        }

    def action_open_job_card(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'job.card',
            'res_id': self.job_card_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Job card -> order
    # ------------------------------------------------------------------
    def _on_job_card_created(self, job_card):
        for order in self:
            order.sudo().write({'job_card_id': job_card.id})
            if order.state == 'new':
                order.sudo()._set_state('confirmed', 'confirmed')
            else:
                order.sudo()._notify_customer('confirmed')

    def _on_job_card_state(self, job_card_state):
        """The linked job card moved: tell the customer, keep the order in step."""
        key = JOB_CARD_KEYS.get(job_card_state)
        for order in self.sudo():
            if key:
                order._notify_customer(key)
            if job_card_state == 'completed' and order.state != 'done':
                order._set_state('done')          # 'completed' already told them
            elif job_card_state == 'cancelled' and order.state != 'cancelled':
                order._set_state('cancelled')
            elif job_card_state in ('draft', 'inspection', 'quotation', 'repair') \
                    and order.state in ('new', 'done', 'cancelled'):
                order._set_state('confirmed')

    # ------------------------------------------------------------------
    # WhatsApp to the customer
    # ------------------------------------------------------------------
    def _status_label(self, key):
        return dict(STATUS_KEYS).get(key, key)

    def _notify_customer(self, key):
        """WhatsApp the customer about this status; the result goes to the chatter."""
        for order in self.sudo():
            site = order.site_id
            if not site or not site.whatsapp_messages or not order.phone:
                continue
            text = self.env['online.service.message']._render(key, {
                'name': order.customer_name or _("customer"),
                'order': order.name,
                'status': self._status_label(key),
                'job_card': order.job_card_id.name or '',
                'site': site.name,
                'track_url': site._track_url(),
                'summary': order.summary or '',
            })
            if not text:
                continue
            status, detail = site._wa_deliver(order.phone, text, order=order)
            order.message_post(
                body=_("WhatsApp to customer (%(status)s): %(result)s",
                       status=self._status_label(key),
                       result={'sent': _("sent"), 'queued': _("queued, the gateway will retry"),
                               'blocked': _("not sent"), 'error': _("failed"),
                               'skipped': _("skipped")}.get(status, status)
                       + (' - %s' % detail if detail else '')),
                message_type='comment', subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Alarm
    # ------------------------------------------------------------------
    @api.model
    def _alarm_users(self):
        group = self.env.ref('mobile_repair.group_mobile_repair_receptionist', raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        return self.env['res.users'].sudo().search([('all_group_ids', 'in', group.ids), ('share', '=', False)])

    def _ring(self):
        """Tell every open Odoo tab to re-check the alarm now (else it polls every 20 s)."""
        for user in self._alarm_users():
            user._bus_send('online_service/refresh', {})

    @api.model
    def alarm_state(self):
        """What the alarm service needs: the new, unopened orders of sites with the alarm on."""
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
            return {'count': 0, 'orders': []}
        orders = self.sudo().search([
            ('state', '=', 'new'),
            ('opened_by_id', '=', False),
            ('site_id.alarm', '=', True),
            ('company_id', 'in', self.env.companies.ids),
        ], limit=20)
        return {
            'count': len(orders),
            'orders': [{'id': o.id, 'name': o.name, 'mode': dict(MODES)[o.mode],
                        'customer': o.customer_name or o.phone or ''} for o in orders],
        }

    # ------------------------------------------------------------------
    # Customer tracking (website "My orders", after the WhatsApp code)
    # ------------------------------------------------------------------
    def _timeline_index(self):
        self.ensure_one()
        jc = self.job_card_id.state if self.job_card_id else False
        if self.state == 'done' or jc == 'completed':
            return 5
        if jc in ('inspection', 'quotation', 'repair'):
            return {'inspection': 2, 'quotation': 3, 'repair': 4}[jc]
        if self.state == 'confirmed' or self.job_card_id:
            return 1
        return 0

    @api.model
    def customer_orders(self, host, phone):
        """Orders of this phone on this website, newest first, with their live status."""
        self._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        digits = digits_of(phone)
        if not site or len(digits) < 7:
            return {'ok': False, 'orders': []}
        orders = self.sudo().search([('site_id', '=', site.id), ('phone_digits', '=', digits)],
                                    order='id desc', limit=30)
        out = []
        for o in orders:
            cancelled = o.state == 'cancelled' or o.job_card_state == 'cancelled'
            idx = o._timeline_index()
            out.append({
                'ref': o.name,
                'mode': o.mode,
                'mode_label': dict(MODES)[o.mode],
                'summary': o.summary or '',
                'lines': [{'device': l.device or '', 'model': l.model or '', 'issue': l.issue,
                           'qty': l.qty} for l in o.line_ids],
                'job_card': o.job_card_id.name or '',
                'cancelled': cancelled,
                'step': idx,
                'status': _("Cancelled") if cancelled else TIMELINE[idx][1],
                'steps': [{'key': k, 'label': label, 'done': not cancelled and i <= idx,
                           'current': not cancelled and i == idx}
                          for i, (k, label) in enumerate(TIMELINE)],
                'created': fields.Datetime.to_string(o.create_date),
                'updated': fields.Datetime.to_string(max(o.write_date, o.job_card_id.write_date or o.write_date)),
            })
        return {'ok': True, 'site': site.name, 'orders': out}


class OnlineServiceOrderLine(models.Model):
    _name = 'online.service.order.line'
    _description = 'Online Service Order Line'

    order_id = fields.Many2one('online.service.order', required=True, ondelete='cascade', index=True)
    device = fields.Char()
    model = fields.Char()
    issue = fields.Char('Repair', required=True)
    qty = fields.Integer(default=1)
