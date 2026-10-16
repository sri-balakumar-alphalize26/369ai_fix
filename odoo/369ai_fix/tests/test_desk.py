# -*- coding: utf-8 -*-
"""The Booking Desk (app/models/fix_desk.py): stages, the cheap poll, the walk from
assign to done through one method, and the bus message that wakes every open desk."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

HOST = 'desk-test.example'
PHONE = '+968 9123 4567'
CUSTOMER = (23.6, 58.45)


@tagged('post_install', '-at_install')
class TestBookingDesk(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['online.service.site'].create({
            'name': 'Desk Test', 'domains': HOST, 'whatsapp_messages': True})
        cls.tech_user = new_test_user(cls.env, login='desk_tech', groups='base.group_user')
        cls.desk_user = new_test_user(
            cls.env, login='desk_recep',
            groups='base.group_user,mobile_repair.group_mobile_repair_receptionist')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Arjun Tech', 'user_id': cls.tech_user.id, 'mobile_phone': '+96890000001'})
        cls.env.company.write({'fs_speed_kmh': 30.0, 'fs_arrival_otp': True,
                               'fs_show_tech_phone': True, 'fs_stale_after_s': 120})
        # any slot does for the label; a one-off far ahead when the database has none
        Slot = cls.env['fix.booking.slot']
        cls.slot = Slot.search([], limit=1) or Slot.create({'date': '2031-01-06', 'start': 20.0, 'end': 21.0})
        cls.Order = cls.env['online.service.order']

    def setUp(self):
        super().setUp()
        self.sent = []
        self.bus = []

        def fake_send(site, phone, text):
            self.sent.append((phone, text))
            return 'sent', ''

        def fake_bus(bus, target, notification_type, message):
            self.bus.append((target, notification_type))

        self.startPatcher(patch.object(type(self.env['online.service.site']), '_wa_send', fake_send))
        self.startPatcher(patch.object(type(self.env['bus.bus']), '_sendone', fake_bus))
        # the database may hold real bookings: every count is read against this baseline
        self.base = self._counts()

    # ------------------------------------------------------------------
    def _book(self, **extra):
        payload = {
            'host': HOST, 'mode': 'doorstep', 'name': 'Ahmed', 'phone': PHONE,
            'area': 'Qurum', 'address': 'Villa 12', 'lat': CUSTOMER[0], 'lng': CUSTOMER[1],
            'lines': [{'device': 'Mobile Phones', 'model': 'iPhone 13', 'issue': 'Screen', 'qty': 1}],
        }
        payload.update(extra)
        result = self.Order.website_create(payload)
        self.assertTrue(result['ok'], result)
        return self.Order.search([('name', '=', result['ref'])])

    def _counts(self, stage='new'):
        return self.Order.fix_desk_load(stage=stage)['counts']

    def _only(self, counts, *stages):
        """Over the baseline, every stage is 0 except the ones named (1 each)."""
        for key, count in counts.items():
            self.assertEqual(count - self.base.get(key, 0), 1 if key in stages else 0,
                             '%s: %s (baseline %s)' % (key, counts, self.base))

    def _row(self, stage, order):
        rows = [r for r in self.Order.fix_desk_load(stage=stage)['rows'] if r['id'] == order.id]
        self.assertEqual(len(rows), 1, 'expected %s in stage %s' % (order.name, stage))
        return rows[0]

    # ------------------------------------------------------------------
    def test_counts_follow_the_booking(self):
        order = self._book()
        self._only(self._counts(), 'new')
        load = self.Order.fix_desk_load(stage='new')
        self.assertIn(order.name, [r['name'] for r in load['rows']])
        self.assertEqual(self._row('new', order)['stage'], 'new')
        self.assertIn('counts', load)
        self.assertTrue(load['since'])
        self.assertEqual(load['ring'] > 0 and load['repeat'] > 0, True)
        self.assertIn(self.employee.id, [t['id'] for t in load['technicians']])
        self.assertNotIn(self.env.company._wb_unassigned_employee().id, [t['id'] for t in load['technicians']])

        order.action_confirm()
        self._only(self._counts(), 'approved')          # confirmed, no time yet

        order.write({'slot_id': self.slot.id, 'slot_date': fields.Date.today(),
                     'slot_booked_on': fields.Datetime.now()})
        self._only(self._counts(), 'booked')            # the customer picked a time
        row = self._row('booked', order)
        self.assertTrue(row['slot_unseen'])
        self.assertTrue(row['slot'])

        order.action_wb_slot_seen()
        self._only(self._counts(), 'to_assign')         # seen; the visit is still draft

        detail = order.fix_desk_detail()
        self.assertEqual(detail['stage'], 'to_assign')
        self.assertIn('assign', detail['actions'])
        self.assertEqual(detail['numbers'][0]['digits'], '96891234567')
        self.assertEqual(detail['visit']['state'], 'draft')
        self.assertIsNone(detail['map'])

    def test_since_skips_the_rows_when_nothing_changed(self):
        self._book()
        first = self.Order.fix_desk_load(stage='new')
        self.assertIsNotNone(first['rows'])
        again = self.Order.fix_desk_load(stage='new', since=first['since'])
        self.assertIsNone(again['rows'])
        self.assertEqual(again['counts'], first['counts'])
        self.assertEqual(again['since'], first['since'])

        self._book(phone='+968 9123 9999')
        changed = self.Order.fix_desk_load(stage='new', since=first['since'])
        self.assertEqual(len(changed['rows']), len(first['rows']) + 1)
        self.assertNotEqual(changed['since'], first['since'])

    def test_walk_from_assign_to_done(self):
        """The whole visit through fix_desk_act, as the receptionist at the desk."""
        booked = self._book()
        booked.action_confirm()
        visit = booked.visit_ids
        self.assertEqual(visit.state, 'draft')
        order = booked.with_user(self.desk_user)

        with self.assertRaises(UserError):
            order.fix_desk_act('assign')                 # no technician chosen
        data = order.fix_desk_act('assign', stage='to_assign', technician_id=self.employee.id)
        self.assertEqual(visit.state, 'assigned')
        self.assertEqual(visit.technician_id, self.employee)
        self.assertEqual(data['detail']['stage'], 'assigned')
        self.assertIn('on_the_way', data['detail']['actions'])
        self._only(data['counts'], 'assigned')
        self.assertIn('/tech?v=', self.sent[-1][1])     # the technician got the link
        self.assertEqual(data['detail']['visit']['arrival_code'], visit.sudo().arrival_code)
        self.assertEqual(data['detail']['visit']['timeline'][0]['current'], True)

        data = order.fix_desk_act('on_the_way', stage='assigned')
        self.assertEqual(visit.state, 'on_the_way')
        self._only(data['counts'], 'live')
        self.assertIn('arrived', data['detail']['actions'])
        self.assertIn('arrived_skip', data['detail']['actions'])

        visit._fs_record_position(CUSTOMER[0], 58.35)
        visit._fs_record_position(CUSTOMER[0], 58.36)
        detail = order.fix_desk_detail()
        self.assertEqual(len(detail['map']['trail']), 2)
        self.assertAlmostEqual(detail['map']['tech']['lng'], 58.36, places=5)
        self.assertEqual(detail['map']['customer'], {'lat': CUSTOMER[0], 'lng': CUSTOMER[1]})
        self.assertTrue(detail['map']['eta_minutes'])
        self.assertTrue(detail['map']['live'])
        self.assertTrue(self._row('live', order)['eta'])

        action = order.fix_desk_act('arrived', stage='live')
        self.assertEqual(action['action']['res_model'], 'fix.service.visit.arrival')   # the code wizard
        self.assertEqual(visit.state, 'on_the_way')
        data = order.fix_desk_act('arrived_skip', stage='live')
        self.assertEqual(visit.state, 'arrived')
        self.assertIn('start', data['detail']['actions'])

        data = order.fix_desk_act('start', stage='live')
        self.assertEqual(visit.state, 'in_progress')
        self._only(data['counts'], 'working')

        data = order.fix_desk_act('done', stage='working')
        self.assertEqual(visit.state, 'done')
        self._only(data['counts'], 'done_today')
        self.assertEqual(data['detail']['actions'], [])
        self.assertTrue(all(step['done'] for step in data['detail']['visit']['timeline']))

        with self.assertRaises(UserError):
            order.fix_desk_act('fly')

    def test_approve_needs_a_new_order(self):
        order = self._book()
        approve = order.fix_desk_act('approve')['action']
        self.assertEqual(approve['res_model'], 'wb.approve.wizard')
        self.assertTrue(approve.get('views'), "the web client needs the views list")
        self.assertEqual(order.opened_by_id, self.env.user)
        order.action_confirm()
        with self.assertRaises(UserError):
            order.fix_desk_act('approve')
        with self.assertRaises(UserError):
            order.fix_desk_act('reject')

    def test_reject_shows_today(self):
        order = self._book()
        self.assertEqual(order.fix_desk_act('reject')['action']['res_model'], 'wb.reject.wizard')
        order._wb_do_reject('No parts for this model')
        self._only(self._counts(), 'rejected')
        self.assertEqual(self._row('rejected', order)['state'], 'cancelled')
        self.assertEqual(order.fix_desk_detail()['reject_reason'], 'No parts for this model')

    def test_bus_wakes_the_desk(self):
        order = self._book()
        self.assertIn(('fix_desk', 'fix_desk/refresh'), self.bus)     # a new booking rings
        self.bus.clear()
        order.action_confirm()
        self.assertIn(('fix_desk', 'fix_desk/refresh'), self.bus)     # confirm rings
        visit = order.visit_ids
        visit.technician_id = self.employee
        visit.action_assign()
        self.bus.clear()
        visit.action_on_the_way()
        self.assertIn(('fix_desk', 'fix_desk/refresh'), self.bus)     # the visit's state changed
        self.bus.clear()
        visit._fs_record_position(23.5, 58.4)                         # first trail point
        self.assertIn(('fix_desk', 'fix_desk/refresh'), self.bus)
        self.bus.clear()
        visit._fs_record_position(23.50009, 58.4)                     # ~10 m: no new point, no wake
        self.assertNotIn(('fix_desk', 'fix_desk/refresh'), self.bus)
