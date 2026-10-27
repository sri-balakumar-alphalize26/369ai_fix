# -*- coding: utf-8 -*-
"""Pick a time from My orders: the signed-in customer picks (or changes) the visit time on the
website, not only from the WhatsApp link. The same slot page and booking as the link
(slot_options / slot_book / parts_answer in online_order_review.py): only the proof differs.
The link proves the customer with its token; here the website server proves them with their
signed-in number (as customer_orders does), and the booking must be theirs on that website.

customer_orders rows get ``time``: what the order page offers (pick, change, a parts question,
waiting for parts), or None when there is nothing to pick.

A new price after the technician's check works the same way: the WhatsApp link's /quote page,
or "Review the price" on My orders (customer_quote, proven by the sign-in); rows get ``quote``.
"""
from odoo import _, api, models
from odoo.exceptions import AccessError

from ...customer.models.online_order import clip, digits_of

# the visit has not started: the time can still be picked or changed
TIME_VISIT_STATES = ('draft', 'assigned')


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    @api.model
    def _wb_from_link(self, host, ref, token):
        """The order already proven by the customer's sign-in (customer_slot below) or opened by staff
        on the Booking Desk (desk_slot), else the link."""
        own = self.env.context.get('fix_customer_order')
        if not own:
            return super()._wb_from_link(host, ref, token)
        order = self.sudo().browse(own).exists()
        if self.env.context.get('fix_slot_by'):           # staff: the desk opened this very order
            site_ok = bool(order)
        else:
            site = self.env['online.service.site']._for_host(host)
            site_ok = bool(order and site and order.site_id == site)
        if not order or not site_ok or order.name != ref:
            return order.browse(), 'unknown'
        if order.state == 'cancelled':
            return order.browse(), 'cancelled'
        return order, ''

    @api.model
    def _wb_customer_order(self, host, phone, ref):
        """The booking `ref` of the signed-in number on this website, or an empty record."""
        site = self.env['online.service.site']._for_host(host)
        digits = digits_of(phone)
        if not site or len(digits) < 7 or not ref:
            return self.sudo().browse()
        return self.sudo().search([('site_id', '=', site.id), ('name', '=', clip(ref, 30)),
                                   ('phone_digits', '=', digits)], limit=1)

    @api.model
    def customer_slot(self, host, phone, ref, action='', slot_id=0, date='', yes=False):
        """The slot page for a signed-in customer: action '' = what the page shows, 'book' = pick
        a window, 'parts' = order the missing part (yes / no). Same answers as the link's."""
        self._check_website_caller()
        order = self._wb_customer_order(host, phone, ref)
        if not order:
            return {'ok': False, 'error': 'unknown'}
        own = self.with_context(fix_customer_order=order.id)
        if action == 'book':
            return own.slot_book(host, order.name, '', slot_id, date)
        if action == 'parts':
            return own.parts_answer(host, order.name, '', bool(yes))
        return own.slot_options(host, order.name, '')

    @api.model
    def customer_quote(self, host, phone, ref, action='', yes=False, choice=None):
        """The new-price page for a signed-in customer (My orders): action '' = what the page shows,
        'answer' = Approve (yes) / Decline, with the grade kept where a part is offered in two
        (`choice`). The same page and answers as the WhatsApp link's /quote page."""
        self._check_website_caller()
        order = self._wb_customer_order(host, phone, ref)
        if not order:
            return {'ok': False, 'error': 'unknown'}
        own = self.with_context(fix_customer_order=order.id)
        if action == 'answer':
            ids = [int(x) for x in (choice or []) if str(x).isdigit()]
            return own.quote_answer(host, order.name, '', bool(yes), choice=ids)
        return own.quote_options(host, order.name, '')

    def _wb_quote_row(self):
        """What My orders offers for a changed price: waiting for the customer's OK (a button that
        opens the price), or None."""
        self.ensure_one()
        order = self.sudo()
        if order.state in ('done', 'cancelled'):
            return None
        cards = order.job_card_ids.filtered(lambda c: c.quote_state == 'waiting')
        if not cards:
            return None
        currency = (order.company_id or self.env.company).currency_id
        return {'state': 'waiting', 'total': sum(cards.mapped(lambda c: c._wb_lines_total())),
                'currency': currency.name, 'decimals': currency.decimal_places,
                # the technician asks to take the device for a lab check (no price yet)
                'lab': order._wb_lab_ask(cards)}

    def desk_slot(self, action='', slot_id=0, date=''):
        """Book a time from the Booking Desk, for the customer (on the phone, or when WhatsApp is
        down): the same windows, places, rules and messages as the customer's own booking; the
        chatter says which staff member booked it. action '' = what the picker shows, 'book'."""
        self.ensure_one()
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
            raise AccessError(_("Only the office books a time for the customer."))
        own = self.with_context(fix_customer_order=self.id, fix_slot_by=self.env.user.name)
        # the booking's own website, so what else follows a booked time (danatfix's staff group line) finds it
        site = self.sudo().site_id
        host = (site._hosts() or [''])[0] if site else ''
        if action == 'book':
            return own.slot_book(host, self.name, '', slot_id, date)
        return own.slot_options(host, self.name, '')

    def _wb_time_row(self):
        """What My orders offers for the visit time, or None (not approved yet, rejected, done,
        cancelled, or the visit has started)."""
        self.ensure_one()
        order = self.sudo()
        if not order.approved_on or order.rejected or order.state in ('done', 'cancelled') \
                or order.job_card_state == 'cancelled':
            return None
        visit = order._fs_current_visit()
        if visit and visit.state not in TIME_VISIT_STATES + ('cancelled',):
            return None
        page = order._wb_page_state()
        return {'state': page, 'label': order.slot_label or '',
                'can_change': page != 'booked' or order._wb_can_change_slot()}

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
            row['time'] = order._wb_time_row() if order else None
            row['quote'] = order._wb_quote_row() if order else None
        return result
