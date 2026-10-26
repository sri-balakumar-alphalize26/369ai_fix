# -*- coding: utf-8 -*-
"""Pick a time from My orders (booking/models/online_order_slot_customer.py): the signed-in
number sees and books the same windows as the WhatsApp link, only for its own booking, and
My orders says what the order page offers."""
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

HOST = 'pick-test.example'
PHONE = '+968 9123 7777'


@tagged('post_install', '-at_install')
class TestPickTime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['online.service.site'].create({'name': 'Pick Test', 'domains': HOST, 'whatsapp_messages': True})
        cls.Order = cls.env['online.service.order']
        cls.env['hr.employee'].create({'name': 'Pick Tech', 'fix_takes_visits': True})   # a place in each window
        Slot = cls.env['fix.booking.slot']
        if not Slot.search_count([]):
            Slot.create({'date': '2031-01-06', 'start': 20.0, 'end': 21.0})

    def setUp(self):
        super().setUp()
        self.startPatcher(patch.object(type(self.env['online.service.site']), '_wa_send', lambda site, phone, text: ('sent', '')))
        self.startPatcher(patch.object(type(self.env['bus.bus']), '_sendone', lambda *a, **k: None))

    def _book(self):
        result = self.Order.website_create({
            'host': HOST, 'mode': 'doorstep', 'name': 'Salim', 'phone': PHONE, 'area': 'Qurum',
            'lines': [{'device': 'Mobile Phones', 'model': 'X1', 'issue': 'Screen', 'qty': 1}]})
        self.assertTrue(result['ok'], result)
        return self.Order.search([('name', '=', result['ref'])])

    def _approve(self, order):
        order.write({'approved_on': fields.Datetime.now(), 'state': 'confirmed', 'parts_state': 'ready'})
        return order

    def _row(self, order, phone=PHONE):
        rows = self.Order.customer_orders(HOST, phone)['orders']
        return next(r for r in rows if r['ref'] == order.name)

    def test_my_orders_offers_the_time_and_books_it(self):
        order = self._book()
        self.assertIsNone(self._row(order)['time'], 'nothing to pick before approval')
        self._approve(order)
        self.assertEqual(self._row(order)['time'], {'state': 'pick', 'label': '', 'can_change': True})

        page = self.Order.customer_slot(HOST, PHONE, order.name)
        self.assertTrue(page['ok'], page)
        self.assertEqual(page['state'], 'pick')
        free = [(d['date'], w['slot_id']) for d in page['days'] for w in d['windows'] if w['free'] > 0]
        if not free:
            self.skipTest('no free slot in this database')
        day, slot = free[0]
        done = self.Order.customer_slot(HOST, PHONE, order.name, action='book', slot_id=slot, date=day)
        self.assertTrue(done['ok'], done)
        self.assertEqual(order.slot_id.id, slot)
        self.assertEqual(fields.Date.to_string(order.slot_date), day)
        row = self._row(order)['time']
        self.assertEqual(row['state'], 'booked')
        self.assertEqual(row['label'], order.slot_label)
        self.assertIn('booked', ' '.join(order.message_ids.mapped('body')))

    def test_only_the_customers_own_booking(self):
        order = self._approve(self._book())
        self.assertEqual(self.Order.customer_slot(HOST, '+968 9999 1111', order.name)['error'], 'unknown')
        self.assertEqual(self.Order.customer_slot('other.example', PHONE, order.name)['error'], 'unknown')
        self.assertEqual(self.Order.customer_slot(HOST, PHONE, 'OS/NOPE')['error'], 'unknown')
        # the link still needs its token: the customer's door is not a way round it
        self.assertEqual(self.Order.slot_options(HOST, order.name, '')['error'], 'unknown')

    def test_staff_book_the_time_on_the_desk(self):
        from odoo.exceptions import AccessError
        from odoo.tests import new_test_user
        order = self._approve(self._book())
        recep = new_test_user(self.env, login='pick_recep', groups='base.group_user,mobile_repair.group_mobile_repair_receptionist')
        clerk = new_test_user(self.env, login='pick_clerk', groups='base.group_user')
        with self.assertRaises(AccessError):
            order.with_user(clerk).desk_slot()
        mine = order.with_user(recep)
        page = mine.desk_slot()
        self.assertTrue(page['ok'], page)
        self.assertEqual(page['state'], 'pick')
        self.assertIn('book_time', order._fix_desk_actions('approved', order._fs_current_visit(), order._fix_desk_cards()))
        free = [(d['date'], w['slot_id']) for d in page['days'] for w in d['windows'] if w['free'] > 0]
        if not free:
            self.skipTest('no free slot in this database')
        done = mine.desk_slot(action='book', slot_id=free[0][1], date=free[0][0])
        self.assertTrue(done['ok'], done)
        self.assertEqual(order.slot_id.id, free[0][1])
        self.assertEqual(order.slot_seen_by_id, recep, "staff who book it have seen it: no alarm")
        self.assertIn('Time booked by', ' '.join(order.message_ids.mapped('body')))

    def test_parts_question_and_cancelled(self):
        order = self._approve(self._book())
        order.parts_state = 'ask'
        self.assertEqual(self._row(order)['time']['state'], 'ask_parts')
        self.assertEqual(self.Order.customer_slot(HOST, PHONE, order.name)['state'], 'ask_parts')
        order.state = 'cancelled'
        self.assertIsNone(self._row(order)['time'])
        self.assertEqual(self.Order.customer_slot(HOST, PHONE, order.name)['error'], 'cancelled')
