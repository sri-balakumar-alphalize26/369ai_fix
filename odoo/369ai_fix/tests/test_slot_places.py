# -*- coding: utf-8 -*-
"""Places in a time window follow the technicians (booking/models/booking_slot.py,
technician_day_off.py): one per employee who takes visits, minus days off, capped by the
slot's "At most"; a full window refuses a booking; a technician off that day is not handed
the visit, by the booking or from the desk."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

HOST = 'places-test.example'
PHONE = '+968 9123 6666'


@tagged('post_install', '-at_install')
class TestSlotPlaces(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Employee = cls.env['hr.employee']
        # this test decides who takes visits: the database's own technicians step aside
        Employee.search([('fix_takes_visits', '=', True)]).write({'fix_takes_visits': False})
        cls.t1 = Employee.create({'name': 'Places Tech 1', 'fix_takes_visits': True, 'mobile_phone': '+96890000011'})
        cls.t2 = Employee.create({'name': 'Places Tech 2', 'fix_takes_visits': True, 'mobile_phone': '+96890000012'})
        cls.office = Employee.create({'name': 'Office Clerk'})
        cls.day = fields.Date.context_today(cls.env['res.users']) + timedelta(days=3)
        # one window of its own, far from the database's slots, on that day
        cls.env['fix.booking.slot'].search([('date', '=', cls.day)]).write({'active': False})
        cls.slot = cls.env['fix.booking.slot'].create({'date': cls.day, 'start': 23.0, 'end': 23.75})
        cls.site = cls.env['online.service.site'].create({'name': 'Places Test', 'domains': HOST, 'whatsapp_messages': True})
        cls.Order = cls.env['online.service.order']

    def setUp(self):
        super().setUp()
        self.startPatcher(patch.object(type(self.env['online.service.site']), '_wa_send', lambda site, phone, text: ('sent', '')))
        self.startPatcher(patch.object(type(self.env['bus.bus']), '_sendone', lambda *a, **k: None))

    def _off(self, tech, day=None):
        return self.env['fix.technician.day.off'].create({'employee_id': tech.id, 'date_from': day or self.day,
                                                          'date_to': day or self.day, 'reason': 'Sick leave'})

    def _book_time(self, phone):
        result = self.Order.website_create({'host': HOST, 'mode': 'doorstep', 'name': 'Places', 'phone': phone, 'area': 'Qurum',
                                            'lines': [{'device': 'Mobile Phones', 'model': 'X1', 'issue': 'Screen', 'qty': 1}]})
        order = self.Order.search([('name', '=', result['ref'])])
        order.write({'approved_on': fields.Datetime.now(), 'state': 'confirmed', 'parts_state': 'ready'})
        token = order._wb_new_slot_link().split('&t=', 1)[1]
        return order, self.Order.slot_book(HOST, order.name, token, self.slot.id, fields.Date.to_string(self.day))

    def test_places_follow_the_technicians(self):
        self.assertEqual(self.slot._places(self.day), 2, 'two technicians, the office clerk does not count')
        self.company.sudo().wb_unassigned_employee_id = self.t2
        self.assertEqual(self.slot._places(self.day), 1, 'the website placeholder never counts')
        self.company.sudo().wb_unassigned_employee_id = False
        self.slot.capacity = 1
        self.assertEqual(self.slot._places(self.day), 1, '"At most" caps the window')
        self.slot.capacity = 0
        self.env['hr.employee'].create({'name': 'Places Tech 3', 'fix_takes_visits': True})
        self.assertEqual(self.slot._places(self.day), 3, 'a new technician adds a place by itself')

    def test_a_day_off_takes_one_place_that_day_only(self):
        self._off(self.t1)
        self.assertEqual(self.slot._places(self.day), 1)
        self.assertEqual(self.slot._places(self.day + timedelta(days=1)), 2)
        self.assertTrue(self.t1._fix_off_on(self.day))
        self.assertFalse(self.t2._fix_off_on(self.day))
        with self.assertRaises(Exception):
            self.env['fix.technician.day.off'].create({'employee_id': self.t2.id, 'date_from': self.day,
                                                       'date_to': self.day - timedelta(days=1), 'reason': 'x'})

    def test_reason_required_and_the_question_before_saving(self):
        DayOff = self.env['fix.technician.day.off']
        with self.assertRaises(Exception):
            DayOff.create({'employee_id': self.t2.id, 'date_from': self.day, 'date_to': self.day})
            DayOff.flush_model()
        Screen = self.env['fix.screen']
        vals = {'employee_id': [self.t2.id, self.t2.name], 'date_from': fields.Date.to_string(self.day),
                'date_to': fields.Date.to_string(self.day), 'reason': 'Training'}
        # no visits then: a plain question
        text = Screen.screen_create_confirm('days_off', vals)
        self.assertIn('Places Tech 2 will be off on', text)
        self.assertIn('(Training)', text)
        self.assertIn('Save this day off?', text)
        self.assertEqual(Screen.screen_create_confirm('days_off', dict(vals, reason='')), '',
                         'nothing to ask until the reason is typed')
        # a visit then: the question lists it, with who is free at that time
        order, booked = self._book_time('+968 9123 6603')
        self.assertTrue(booked['ok'], booked)
        visit = order._fs_current_visit()
        visit.sudo().technician_id = self.t2
        ask = Screen.screen_create_confirm('days_off', vals)
        self.assertEqual([v['id'] for v in ask['visits']], [visit.id])
        row = ask['visits'][0]
        self.assertTrue(row['movable'])
        self.assertEqual([o['id'] for o in row['options']], [self.t1.id], 'free then; the one going off is not offered')
        self.assertEqual(row['pick'], self.t1.id)
        # saving with the pick moves the visit to them, as Assign on the desk
        Screen.screen_save('days_off', False, vals, {}, {'reassign': {str(visit.id): self.t1.id}})
        self.assertEqual((visit.state, visit.technician_id), ('assigned', self.t1))
        self.assertIn('the visit went to Places Tech 1', ' '.join(order.message_ids.mapped('body')))
        # the desk's assign list knows who is off that day
        self._off(self.t1)
        techs = {t['id']: t for t in self.Order._fix_desk_technicians()}
        self.assertIn(fields.Date.to_string(self.day), techs[self.t1.id]['off'])
        self.assertIn(fields.Date.to_string(self.day), techs[self.t2.id]['off'], 'the day off saved above')
        self.assertNotIn(fields.Date.to_string(self.day + timedelta(days=1)), techs[self.t2.id]['off'])

    def test_nobody_chosen_sends_the_visit_back_to_the_desk(self):
        order, booked = self._book_time('+968 9123 6604')
        self.assertTrue(booked['ok'], booked)
        order._fix_desk_assign(self.t2.id)
        visit = order._fs_current_visit()
        self.assertEqual(visit.state, 'assigned')
        self.env['fix.screen'].screen_save('days_off', False, {
            'employee_id': [self.t2.id, self.t2.name], 'date_from': fields.Date.to_string(self.day),
            'date_to': fields.Date.to_string(self.day), 'reason': 'Sick leave'}, {}, {'reassign': {str(visit.id): 0}})
        self.assertEqual(visit.state, 'draft')
        self.assertNotEqual(visit.technician_id, self.t2)
        self.assertIn('back to "To assign"', ' '.join(order.message_ids.mapped('body')))

    def test_a_full_window_refuses_the_booking(self):
        self._off(self.t1)                                   # one place that day
        _first, ok = self._book_time('+968 9123 6601')
        self.assertTrue(ok['ok'], ok)
        _second, full = self._book_time('+968 9123 6602')
        self.assertEqual(full, {'ok': False, 'error': 'full'})

    def test_a_technician_off_that_day_is_not_handed_the_visit(self):
        self._off(self.t1)
        result = self.Order.website_create({'host': HOST, 'mode': 'doorstep', 'name': 'Places', 'phone': PHONE, 'area': 'Qurum',
                                            'lines': [{'device': 'Mobile Phones', 'model': 'X1', 'issue': 'Screen', 'qty': 1}]})
        order = self.Order.search([('name', '=', result['ref'])])
        order.write({'approved_on': fields.Datetime.now(), 'parts_state': 'ready'})
        order.action_confirm()
        visit = order.visit_ids
        visit.technician_id = self.t1                        # chosen at approval
        token = order._wb_new_slot_link().split('&t=', 1)[1]
        booked = self.Order.slot_book(HOST, order.name, token, self.slot.id, fields.Date.to_string(self.day))
        self.assertTrue(booked['ok'], booked)
        self.assertEqual(visit.state, 'draft', 'waits on the desk')
        self.assertIn('is off on', ' '.join(order.message_ids.mapped('body')))
        # the desk refuses them too, and takes the other one
        with self.assertRaises(UserError):
            order._fix_desk_assign(self.t1.id)
        order._fix_desk_assign(self.t2.id)
        self.assertEqual((visit.state, visit.technician_id), ('assigned', self.t2))
