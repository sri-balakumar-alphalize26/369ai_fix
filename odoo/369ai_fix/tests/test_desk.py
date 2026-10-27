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
            'name': 'Arjun Tech', 'user_id': cls.tech_user.id, 'mobile_phone': '+96890000001',
            'fix_takes_visits': True})   # a place in every time window
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

        # Start opens "Before you start" while the safety check and photos are not done
        action = order.fix_desk_act('start', stage='live')
        self.assertEqual(action['action']['res_model'], 'fix.service.visit')
        self.assertTrue(action['action']['views'])
        self.assertEqual(visit.state, 'arrived')
        data = order.with_context(fix_checks_passed=True).fix_desk_act('start', stage='live')
        self.assertEqual(visit.state, 'in_progress')
        self._only(data['counts'], 'working')

        data = order.fix_desk_act('done', stage='working')
        self.assertEqual(visit.state, 'done')
        self._only(data['counts'], 'done_today')
        self.assertEqual(data['detail']['actions'], [])
        self.assertTrue(all(step['done'] for step in data['detail']['visit']['timeline']))

        with self.assertRaises(UserError):
            order.fix_desk_act('fly')

    def test_upgrade_opens_the_booking_desk(self):
        """Upgrade in Apps reloads on 369 ai Fix's Booking Desk, not on the first app (Discuss)."""
        from odoo.addons.base.models.ir_module import IrModuleModule
        reload = {'type': 'ir.actions.client', 'tag': 'reload', 'params': {'menu_id': 1}}
        Modules = self.env['ir.module.module']
        with patch.object(IrModuleModule, 'button_immediate_upgrade', lambda self: dict(reload)):
            ours = Modules.search([('name', '=', '369ai_fix')]).button_immediate_upgrade()
            other = Modules.search([('name', '=', 'base')]).button_immediate_upgrade()
        self.assertEqual(ours['params'], {'menu_id': self.env.ref('369ai_fix.menu_fix_root').id,
                                          'action_id': self.env.ref('369ai_fix.action_fix_desk').id})
        self.assertEqual(other['params'], {'menu_id': 1})         # another app: Odoo's own choice

    def test_search_every_booking(self):
        """The desk's search box: name, booking number (with or without OS/), visit number; with the count."""
        order = self._book(name='Zarqa Searchtest')
        order.action_confirm()                                       # makes the visit
        visit = order.visit_ids[:1]
        self.assertTrue(visit)
        Order = self.Order.with_user(self.desk_user)
        found = Order.fix_desk_search('zarqa searchtest')
        self.assertEqual(found['count'], 1)
        self.assertEqual(found['rows'][0]['id'], order.id)
        self.assertTrue(found['rows'][0]['stage_label'])
        digits = order.name.split('/')[-1]
        self.assertIn(order.id, [r['id'] for r in Order.fix_desk_search(order.name)['rows']])
        self.assertIn(order.id, [r['id'] for r in Order.fix_desk_search(digits)['rows']])
        by_visit = Order.fix_desk_search(visit.name)
        self.assertIn(order.id, [r['id'] for r in by_visit['rows']])
        self.assertIn(visit.name, by_visit['rows'][0]['visits'])
        self.assertEqual(Order.fix_desk_search('x'), {'count': 0, 'rows': []})      # one letter: nothing yet
        self.assertEqual(Order.fix_desk_search('no-such-customer-qq')['count'], 0)

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

    # ------------------------------------------------------------------ booked without a brand
    def _tablets(self):
        """A category with one brand, two close model names and a priced repair."""
        category = self.env['device.category'].create({'name': 'Desk Tablets'})
        brand = self.env['device.brand'].create({'name': 'Deskapple', 'category_id': category.id})
        series = self.env['device.series'].create({'name': 'iPad Pro', 'brand_id': brand.id})
        m4 = self.env['device.model'].create({'name': 'iPad Pro 13-inch (M4)', 'series_id': series.id})
        self.env['device.model'].create({'name': 'iPad Pro 13-inch M4 (2024)', 'series_id': series.id})
        repair = self.env['product.product'].create({
            'name': 'Desk Screen / glass', 'type': 'service', 'sale_ok': True, 'lst_price': 45.0,
            'repair_category_ids': [(6, 0, category.ids)]})
        return category, brand, m4, repair

    def test_brand_found_from_the_typed_model(self):
        """A cart saved from the site's own list sends names only: Odoo finds the device."""
        category, brand, m4, repair = self._tablets()
        order = self._book(lines=[{'device': 'Tablets & iPads', 'model': 'Deskapple iPad iPad Pro 13" (M4)',
                                   'issue': repair.name, 'qty': 1, 'category_id': category.id,
                                   'product_id': repair.id}])
        self.assertEqual((order.line_ids.brand_id, order.line_ids.model_id), (brand, m4))
        card = order.job_card_ids
        self.assertEqual((card.brand_id, card.model_id), (brand, m4))
        self.assertEqual(card.service_line_ids.mapped('unit_price'), [45.0])

    def test_approve_makes_the_missing_job_card(self):
        category, brand, m4, repair = self._tablets()
        order = self._book(lines=[{'device': 'Tablets & iPads', 'model': 'My tablet', 'issue': repair.name,
                                   'qty': 1, 'category_id': category.id, 'product_id': repair.id}])
        self.assertFalse(order.job_card_ids)                     # no brand: no job card
        Wizard = self.env['wb.approve.wizard'].with_user(self.desk_user)
        wizard = Wizard.create({'order_id': order.id})
        self.assertTrue(wizard.needs_card)
        self.assertEqual(wizard.category_id, category)
        self.assertFalse(wizard.brand_id)                        # nothing to match in "My tablet"
        with self.assertRaises(UserError):
            wizard.action_confirm()                              # the brand is asked for
        Wizard.create({'order_id': order.id, 'brand_id': brand.id, 'model_id': m4.id}).action_confirm()
        card = order.job_card_ids
        self.assertEqual((card.brand_id, card.model_id), (brand, m4))
        self.assertEqual(card.service_line_ids.product_id, repair)
        self.assertEqual(order.state, 'confirmed')
        self.assertTrue(order.approved_on)

    def test_approve_guesses_the_device(self):
        category, brand, m4, repair = self._tablets()
        order = self._book(lines=[{'device': 'Tablets & iPads', 'model': 'Deskapple iPad Pro 13" (M4)',
                                   'issue': repair.name, 'qty': 1, 'category_id': category.id}])
        order.line_ids.write({'brand_id': False, 'series_id': False, 'model_id': False})
        wizard = self.env['wb.approve.wizard'].create({'order_id': order.id})
        self.assertEqual((wizard.brand_id, wizard.model_id), (brand, m4))

    def test_approve_card_without_a_repair(self):
        order = self._book_with_card()                           # the repair is a name only: no line
        self.assertFalse(order.job_card_ids.service_line_ids)
        with self.assertRaisesRegex(UserError, 'no repair on it yet'):
            order._wb_do_approve()

    # ------------------------------------------------------------------ the technician chosen at approval
    def _book_with_card(self):
        category = self.env['device.category'].create({'name': 'Desk Phones'})
        brand = self.env['device.brand'].create({'name': 'Desk Brand', 'category_id': category.id})
        order = self._book(lines=[{'device': 'Mobile Phones', 'model': 'X1', 'issue': 'Screen', 'qty': 1,
                                   'category_id': category.id, 'brand_id': brand.id}])
        self.assertTrue(order.job_card_ids)
        return order

    def _approve(self, order, technician=None):
        """As the Approve pop-up does: the technician (if chosen) on the job card, then confirmed."""
        if technician:
            order.job_card_ids.write({'assigned_to': technician.id})
        order.action_confirm()

    def _pick_time(self, order):
        """The customer picks the first free window on the slot page."""
        token = order._wb_new_slot_link().split('&t=', 1)[1]
        page = self.Order.slot_options(HOST, order.name, token)
        free = [(d['date'], w['slot_id']) for d in page.get('days', []) for w in d['windows'] if w['free'] > 0]
        if not free:
            day = fields.Date.add(fields.Date.context_today(order), days=2)
            self.env['fix.booking.slot'].create({'date': day, 'start': 23.0, 'end': 23.75, 'capacity': 5})
            page = self.Order.slot_options(HOST, order.name, token)
            free = [(d['date'], w['slot_id']) for d in page['days'] for w in d['windows'] if w['free'] > 0]
        result = self.Order.slot_book(HOST, order.name, token, free[0][1], free[0][0])
        self.assertTrue(result['ok'], result)

    def test_chosen_technician_gets_the_visit_with_the_time(self):
        order = self._book_with_card()
        self._approve(order, self.employee)
        visit = order.visit_ids
        self.assertEqual((visit.state, visit.technician_id), ('draft', self.employee))
        detail = order.fix_desk_detail()
        self.assertEqual(detail['stage'], 'approved')
        self.assertNotIn('assign', detail['actions'])          # no time yet: no link without a time
        before = len(self.sent)
        self._pick_time(order)
        self.assertEqual(visit.state, 'assigned')               # no second Assign on the desk
        self.assertTrue(any('90000001' in phone for phone, _text in self.sent[before:]), self.sent[before:])
        self._only(self._counts(), 'booked')                    # the "time booked" alarm still rings
        order.action_wb_slot_seen()
        self._only(self._counts(), 'assigned')

    def test_no_technician_chosen_the_desk_asks(self):
        order = self._book_with_card()
        self._approve(order)
        self._pick_time(order)
        self.assertEqual(order.visit_ids.state, 'draft')
        order.action_wb_slot_seen()
        self._only(self._counts(), 'to_assign')
        self.assertIn('assign', order.fix_desk_detail()['actions'])

    def test_whatsapp_tab_shows_what_was_sent(self):
        """The office reads exactly what the customer and the technician got, links included."""
        order = self._book_with_card()
        self._approve(order, self.employee)
        self._pick_time(order)
        rows = order.fix_desk_detail()['whatsapp']
        self.assertTrue(rows)
        self.assertEqual(rows, sorted(rows, key=lambda r: r['id']))           # oldest first, like a chat
        to_customer = [r for r in rows if r['who'] == 'customer']
        to_tech = [r for r in rows if r['who'] == 'technician']
        self.assertTrue(to_customer and to_tech, rows)
        self.assertTrue(all(r['body'] and r['status'] == 'sent' for r in rows))
        self.assertIn('/tech?', to_tech[-1]['body'])                           # the technician's page link
        # the same text that went out
        sent_texts = [text for _phone, text in self.sent]
        self.assertTrue(all(r['body'] in sent_texts for r in rows))
        # not sent when WhatsApp is down: kept as waiting, still readable
        with patch.object(type(self.env['online.service.site']), '_wa_send', lambda *a, **k: ('queued', 'not connected')):
            order._wb_notify('slot_booked', slot=order.slot_label)
        last = order.fix_desk_detail()['whatsapp'][-1]
        self.assertEqual((last['status'], last['who']), ('queued', 'customer'))
        self.assertTrue(last['body'])

    def test_my_orders_code_in_test_mode(self):
        """Test mode (this computer): the My orders code is the test code and nothing is sent;
        off (live): a random code goes on WhatsApp and the test code is refused."""
        self._book()
        Otp, ICP = self.env['online.service.otp'], self.env['ir.config_parameter'].sudo()
        ICP.set_param('369ai_fix.test_login_code', '123456')
        before = len(self.sent)
        self.assertTrue(Otp.otp_request(HOST, PHONE)['ok'])
        self.assertEqual(len(self.sent), before)                     # nothing sent
        self.assertTrue(Otp.otp_verify(HOST, PHONE, '123456')['ok'])
        ICP.set_param('369ai_fix.test_login_code', False)
        self.assertTrue(Otp.otp_request(HOST, PHONE)['ok'])
        self.assertEqual(len(self.sent), before + 1)                 # the real code went out
        self.assertNotIn('123456', self.sent[-1][1])
        self.assertFalse(Otp.otp_verify(HOST, PHONE, '123456')['ok'])

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
