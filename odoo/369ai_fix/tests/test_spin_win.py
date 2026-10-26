# -*- coding: utf-8 -*-
"""Spin & Win (website/models/spin_win.py, spin_booking.py, spin_visit.py): Odoo picks the
prize by chance and monthly limit, one spin per customer (or number) in the window, the win is
saved on the customer with its own code, it goes on the next booking as a free line, the
technician marks it given, and the website's switch stops all of it."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .test_visit import DoorstepCase, HOST, PHONE


@tagged('post_install', '-at_install')
class TestSpinWin(DoorstepCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Win = cls.env['fix.spin.win']
        cls.Order = cls.env['online.service.order']
        Item = cls.env['fix.site.item']
        cls.clean = Item.create({'site_id': cls.site.id, 'kind': 'wheel', 'sequence': 10, 'name2': 'Free', 'name': 'Cleaning',
                                 'text': 'Free device cleaning', 'code': 'SPIN-CLEAN', 'chance': 60})
        cls.diag = Item.create({'site_id': cls.site.id, 'kind': 'wheel', 'sequence': 20, 'name2': 'Free', 'name': 'Diagnosis',
                                'text': 'Free diagnosis', 'code': 'SPIN-DIAG', 'chance': 30, 'free_visit': True})
        cls.pick = Item.create({'site_id': cls.site.id, 'kind': 'wheel', 'sequence': 30, 'name2': 'Free', 'name': 'Pickup',
                                'text': 'Free pickup', 'code': 'SPIN-PICK', 'chance': 10, 'month_limit': 1, 'valid_days': 3})
        cls.fast = Item.create({'site_id': cls.site.id, 'kind': 'wheel', 'sequence': 40, 'name2': 'Priority', 'name': 'Slot',
                                'text': 'Priority slot', 'code': 'SPIN-FAST', 'chance': 0})
        cls.partner = cls.env['res.partner'].create({'name': 'Ahmed', 'phone': PHONE})
        cls.other = cls.env['res.partner'].create({'name': 'Salim', 'phone': '+968 9999 0000'})
        cls.category = cls.env['device.category'].create({'name': 'Spin Phones'})
        cls.brand = cls.env['device.brand'].create({'name': 'Spin Brand', 'category_id': cls.category.id})

    def _spin(self, partner=None, ip='10.0.0.1', phone=None):
        partner = partner or self.partner
        return self.Win.website_spin({'host': HOST, 'partner_id': partner.id, 'phone': phone or partner.phone, 'ip': ip})

    def _roll(self, value):
        return patch.object(type(self.Win), '_roll', lambda self, total: value)

    def _book_signed_in(self, partner=None, **extra):
        partner = partner or self.partner
        lines = [{'device': 'Mobile Phones', 'model': 'X1', 'issue': 'Screen', 'qty': 1,
                  'category_id': self.category.id, 'brand_id': self.brand.id}]
        return self._book(partner_id=partner.id, lines=lines, **extra)

    # ------------------------------------------------------------------ the draw
    def test_odds_and_show_only(self):
        # 60 / 30 / 10 / 0: the roll walks the slices in order; 0% is never reached
        with self._roll(10):
            self.assertEqual(self.Win._pick(self.site), self.clean)
        with self._roll(59.9):
            self.assertEqual(self.Win._pick(self.site), self.clean)
        with self._roll(60):
            self.assertEqual(self.Win._pick(self.site), self.diag)
        with self._roll(95):
            self.assertEqual(self.Win._pick(self.site), self.pick)
        with self._roll(99.999):
            self.assertEqual(self.Win._pick(self.site), self.pick)
        # a hidden prize is out of the draw; with every chance at 0 nothing is won
        self.clean.active = False
        with self._roll(0):
            self.assertEqual(self.Win._pick(self.site), self.diag)
        (self.diag | self.pick).write({'chance': 0})
        self.assertFalse(self.Win._pick(self.site))
        self.assertEqual(self._spin()['error'], 'paused')

    def test_month_limit(self):
        with self._roll(95):
            first = self._spin()
        self.assertTrue(first['ok'], first)
        self.assertEqual(first['win']['item_id'], self.pick.id)
        self.assertTrue(first['win']['code'].startswith('SPIN-PICK-'))
        win = self.Win.browse(first['win']['id'])
        self.assertEqual(win.valid_until, fields.Date.add(fields.Date.context_today(self.Win), days=3), "the prize's own validity")
        # the pickup has its one win this month: the same roll now lands on the diagnosis
        with self._roll(95):
            self.assertEqual(self.Win._pick(self.site), self.diag)

    def test_one_spin_per_customer_and_per_number(self):
        with self._roll(0):
            first = self._spin()
        self.assertTrue(first['ok'])
        self.assertNotIn('again', first)
        win = self.Win.browse(first['win']['id'])
        self.assertEqual(win.partner_id, self.partner)
        self.assertEqual(win.prize, 'Free device cleaning')
        self.assertEqual(win.state, 'won')
        self.assertEqual(win.valid_until, fields.Date.add(fields.Date.context_today(self.Win), days=14))
        self.assertEqual(self.partner.spin_win_count, 1)
        # the same customer again: the same win, no new spin
        again = self._spin()
        self.assertTrue(again.get('again'))
        self.assertEqual(again['win']['id'], win.id)
        # another account with the same number: still the same win
        twin = self.env['res.partner'].create({'name': 'Ahmed again', 'phone': '00968 91234567'})
        same = self._spin(partner=twin, phone='9123 4567')
        self.assertTrue(same.get('again'))
        self.assertEqual(same['win']['id'], win.id)
        self.assertEqual(self.Win.search_count([('site_id', '=', self.site.id)]), 1)
        # another customer spins their own
        with self._roll(0):
            other = self._spin(partner=self.other)
        self.assertNotEqual(other['win']['id'], win.id)
        # after the window, the first customer may spin again
        win.won_on = fields.Datetime.now() - timedelta(days=31)
        with self._roll(0):
            fresh = self._spin()
        self.assertNotIn('again', fresh)
        self.assertNotEqual(fresh['win']['id'], win.id)
        self.assertEqual(self.Win.website_current({'host': HOST, 'partner_id': self.partner.id})['win']['id'], fresh['win']['id'])

    def test_ip_limit_and_sign_in(self):
        self.assertEqual(self.Win.website_spin({'host': HOST, 'ip': '1.1.1.1'})['error'], 'sign in')
        for i in range(10):
            partner = self.env['res.partner'].create({'name': 'P%d' % i, 'phone': '+968 9000 00%02d' % i})
            with self._roll(0):
                self.assertTrue(self._spin(partner=partner, ip='1.1.1.1')['ok'])
        self.assertEqual(self._spin(ip='1.1.1.1')['error'], 'too many')
        self.assertTrue(self._spin(ip='2.2.2.2')['ok'])

    # ------------------------------------------------------------------ claiming
    def test_prize_on_the_booking_and_the_job_card(self):
        with self._roll(60):
            spun = self._spin()
        win = self.Win.browse(spun['win']['id'])
        order = self._book_signed_in(spin_win_id=win.id)
        self.assertEqual(order.spin_win_id, win)
        self.assertEqual(win.state, 'used')
        self.assertEqual(win.order_id, order)
        card = order.job_card_ids
        self.assertEqual(len(card), 1)
        free = card.service_line_ids.filtered(lambda l: 'Spin & Win' in (l.description or ''))
        self.assertEqual(len(free), 1)
        self.assertEqual(free.unit_price, 0.0)
        self.assertIn('Free diagnosis', free.description)
        self.assertEqual(card.inspection_type, 'free', 'the prize makes the visit free')
        self.assertIn('Spin &amp; Win prize', ' '.join(order.message_ids.mapped('body')))
        # the desk and the customer's contact know it
        self.assertEqual(order.fix_desk_detail()['prize']['code'], win.code)
        self.assertTrue(order.fix_desk_detail()['prize']['on_booking'])
        self.assertEqual(self.partner.spin_win_ids, win)
        # a second booking cannot use it again
        second = self._book_signed_in(spin_win_id=win.id, ref='AGAIN1')
        self.assertFalse(second.spin_win_id)
        self.assertIn('already used', ' '.join(second.message_ids.mapped('body')))

    def test_typed_code_and_the_coupon_check(self):
        with self._roll(0):
            spun = self._spin()
        win = self.Win.browse(spun['win']['id'])
        check = self.Win.website_coupon({'host': HOST, 'code': win.code.lower(), 'partner_id': self.partner.id})
        self.assertTrue(check['known'] and check['valid'], check)
        self.assertEqual(check['prize'], 'Free device cleaning')
        self.assertFalse(self.Win.website_coupon({'host': HOST, 'code': '369FIX'})['known'])
        # typed in the coupon box, it is used like the cart's
        order = self._book_signed_in(coupon=win.code)
        self.assertEqual(order.spin_win_id, win)
        self.assertEqual(order.coupon, win.code)

    def test_refusals_leave_the_booking_alone(self):
        with self._roll(0):
            spun = self._spin()
        win = self.Win.browse(spun['win']['id'])
        # another customer's booking
        other = self._book_signed_in(partner=self.other, spin_win_id=win.id, ref='OTHER1')
        self.assertFalse(other.spin_win_id)
        self.assertEqual(win.state, 'won')
        self.assertIn('another customer', ' '.join(other.message_ids.mapped('body')))
        # not signed in
        anon = self._book(coupon=win.code, ref='ANON01')
        self.assertFalse(anon.spin_win_id)
        self.assertIn('sign in', ' '.join(anon.message_ids.mapped('body')))
        # expired
        win.valid_until = fields.Date.context_today(self.Win) - timedelta(days=1)
        self.assertEqual(win.state, 'expired')
        late = self._book_signed_in(spin_win_id=win.id, ref='LATE01')
        self.assertFalse(late.spin_win_id)
        self.assertIn('expired', ' '.join(late.message_ids.mapped('body')))
        self.assertFalse(self.Win.website_coupon({'host': HOST, 'code': win.code, 'partner_id': self.partner.id})['valid'])
        # a shop code is not a prize: nothing posted, the code stays on the order
        plain = self._book_signed_in(coupon='369FIX', ref='PLAIN1')
        self.assertEqual(plain.coupon, '369FIX')
        self.assertNotIn('Win', ' '.join(plain.message_ids.mapped('body')))

    def test_technician_marks_it_given(self):
        with self._roll(0):
            spun = self._spin()
        win = self.Win.browse(spun['win']['id'])
        order = self._book_signed_in(spin_win_id=win.id)
        order.action_confirm()
        visit = order.visit_ids
        visit.technician_id = self.employee
        visit.action_assign()
        page = visit._fs_tech_view()
        self.assertEqual(page['prize'], {'id': win.id, 'prize': 'Free device cleaning', 'code': win.code, 'given': False, 'given_by': ''})
        early = visit._fs_tech_do('prize_given')
        self.assertFalse(early['ok'], 'only while working')
        visit.sudo().write({'state': 'in_progress', 'started_on': fields.Datetime.now()})
        page = visit._fs_tech_do('prize_given')
        self.assertTrue(page['ok'], page)
        self.assertTrue(page['prize']['given'])
        self.assertEqual(win.state, 'given')
        self.assertEqual(win.given_by_id, self.env.user)
        self.assertIn('Prize given', ' '.join(visit.message_ids.mapped('body')))
        self.assertTrue(order.spin_given)
        self.assertEqual(self.Win.search([('state', '=', 'given')]), win)
        self.assertNotIn(win, self.Win.search([('state', 'in', ('won', 'used'))]))

    # ------------------------------------------------------------------ the switch
    def test_switch_off_stops_everything(self):
        with self._roll(0):
            spun = self._spin()
        win = self.Win.browse(spun['win']['id'])
        self.site.wheel_show = False
        self.assertEqual(self._spin(partner=self.other)['error'], 'off')
        self.assertEqual(self.Win.website_current({'host': HOST, 'partner_id': self.partner.id})['error'], 'off')
        self.assertEqual(self.Win.website_coupon({'host': HOST, 'code': win.code})['error'], 'off')
        order = self._book_signed_in(spin_win_id=win.id, coupon=win.code)
        self.assertFalse(order.spin_win_id)
        self.assertEqual(win.state, 'won', 'the win is kept, untouched')
        self.assertFalse(order.job_card_ids.service_line_ids.filtered(lambda l: 'Spin & Win' in (l.description or '')))
        self.assertIsNone(order.fix_desk_detail()['prize'])
        self.assertFalse(self.Order.website_content(HOST)['site']['wheel']['show'])
        order.action_confirm()
        visit = order.visit_ids
        visit.technician_id = self.employee
        self.assertNotIn('prize', visit._fs_tech_view())
        # on again: the same win is still there to use
        self.site.wheel_show = True
        self.assertEqual(self.Win.website_current({'host': HOST, 'partner_id': self.partner.id})['win']['id'], win.id)
        self.assertTrue(self.Order.website_content(HOST)['site']['wheel']['show'])
        self.assertEqual(self.Order.website_content(HOST)['site']['wheel']['slices'][0]['id'], self.clean.id)
