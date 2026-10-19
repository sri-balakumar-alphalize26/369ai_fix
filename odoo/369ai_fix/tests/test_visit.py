# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

from ..visits.models.geo import metres, parse_map_link

HOST = 'fs-test.example'
PHONE = '+968 9123 4567'
CUSTOMER = (23.6, 58.45)


class DoorstepCase(TransactionCase):
    """A doorstep website, a technician and the helpers to book and visit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['online.service.site'].create({
            'name': 'FS Test', 'domains': HOST, 'whatsapp_messages': True})
        cls.tech_user = new_test_user(cls.env, login='fs_tech', groups='base.group_user')
        cls.other_user = new_test_user(cls.env, login='fs_other', groups='base.group_user')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Arjun Tech', 'user_id': cls.tech_user.id, 'mobile_phone': '+96890000001'})
        cls.env.company.write({'fs_speed_kmh': 30.0, 'fs_arrival_otp': True,
                               'fs_show_tech_phone': True, 'fs_stale_after_s': 120})

    def setUp(self):
        super().setUp()
        self.sent = []

        def fake_send(site, phone, text):
            self.sent.append((phone, text))
            return 'sent', ''

        self.startPatcher(patch.object(type(self.env['online.service.site']), '_wa_send', fake_send))

    # ------------------------------------------------------------------
    def _book(self, **extra):
        payload = {
            'host': HOST, 'mode': 'doorstep', 'name': 'Ahmed', 'phone': PHONE,
            'area': 'Qurum', 'address': 'Villa 12', 'lat': CUSTOMER[0], 'lng': CUSTOMER[1],
            'lines': [{'device': 'Mobile Phones', 'model': 'iPhone 13', 'issue': 'Screen', 'qty': 1}],
        }
        payload.update(extra)
        result = self.env['online.service.order'].website_create(payload)
        self.assertTrue(result['ok'], result)
        return self.env['online.service.order'].search([('name', '=', result['ref'])])

    def _visit(self, **extra):
        order = self._book(**extra)
        order.action_confirm()
        visit = order.visit_ids
        self.assertEqual(len(visit), 1)
        visit.technician_id = self.employee
        return order, visit

    def _track(self):
        return self.env['online.service.order'].customer_orders(HOST, PHONE)['orders'][0]['visit']



@tagged('post_install', '-at_install')
class TestDoorstepVisit(DoorstepCase):

    def test_website_point_is_kept(self):
        order = self._book()
        self.assertAlmostEqual(order.customer_lat, CUSTOMER[0], places=5)
        self.assertAlmostEqual(order.customer_lng, CUSTOMER[1], places=5)
        self.assertEqual(order.location_source, 'website')
        self.assertTrue(order.map_url)

        bad = self._book(lat=999, lng=58.4, phone='+968 9123 9999')
        self.assertFalse(bad.customer_lat)
        self.assertFalse(bad.location_source)

    def test_confirm_makes_a_draft_visit_for_doorstep_only(self):
        order = self._book()
        self.assertFalse(order.visit_ids)
        order.action_confirm()
        visit = order.visit_ids
        self.assertEqual(visit.state, 'draft')
        self.assertEqual(visit.address, 'Villa 12')
        self.assertAlmostEqual(visit.customer_lat, CUSTOMER[0], places=5)
        self.assertEqual(visit.site_id, self.site)
        self.assertTrue(visit.name.startswith('VIS/'))

        pickup = self._book(mode='pickup', phone='+968 9123 8888')
        pickup.action_confirm()
        self.assertFalse(pickup.visit_ids)

    def test_steps_set_times_and_send_whatsapp(self):
        _order, visit = self._visit()
        visit.action_assign()
        self.assertEqual(visit.state, 'assigned')
        self.assertTrue(visit.assigned_on)
        code = visit.sudo().arrival_code
        self.assertRegex(code, r'^\d{4}$')
        # The customer's message, then the technician's link
        self.assertIn(code, self.sent[-2][1])
        self.assertIn('Arjun Tech', self.sent[-2][1])
        self.assertEqual(self.sent[-1][0], '+96890000001')
        self.assertIn('/tech?v=', self.sent[-1][1])
        self.assertNotIn(code, self.sent[-1][1])

        visit.action_on_the_way()
        self.assertEqual(visit.state, 'on_the_way')
        self.assertTrue(visit.departed_on)

        wrong = '0000' if code != '0000' else '1111'
        result = visit._fs_arrive(code=wrong)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'wrong_code')
        self.assertEqual(visit.arrival_tries, 1)
        self.assertEqual(visit.state, 'on_the_way')

        self.assertTrue(visit._fs_arrive(code=code)['ok'])
        self.assertEqual(visit.state, 'arrived')
        self.assertTrue(visit.arrived_on)
        self.assertTrue(visit.arrival_verified_on)

        # (the safety check and device photos before work: test_visit_checks)
        visit.with_context(fix_checks_passed=True).action_start()
        self.assertTrue(visit.started_on)
        visit.action_done()
        self.assertEqual(visit.state, 'done')
        self.assertTrue(visit.done_on)

    def test_arrival_code_locks_after_five_wrong_tries(self):
        _order, visit = self._visit()
        visit.action_assign()
        code = visit.sudo().arrival_code
        wrong = '0000' if code != '0000' else '1111'
        for _i in range(5):
            visit._fs_arrive(code=wrong)
        result = visit._fs_arrive(code=code)
        self.assertEqual(result['error'], 'locked')
        self.assertEqual(visit.state, 'assigned')
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        self.assertEqual(visit.state, 'arrived')

    def test_wizard_keeps_wrong_try_and_reopens(self):
        _order, visit = self._visit()
        visit.action_assign()
        action = visit.action_arrived()
        self.assertEqual(action['res_model'], 'fix.service.visit.arrival')
        code = visit.sudo().arrival_code
        wizard = self.env['fix.service.visit.arrival'].create({
            'visit_id': visit.id, 'code': '0000' if code != '0000' else '1111'})
        again = wizard.action_confirm()
        self.assertEqual(again['res_id'], wizard.id)
        self.assertTrue(wizard.message)
        wizard.code = code
        wizard.action_confirm()
        self.assertEqual(visit.state, 'arrived')

    def test_positions_and_trail(self):
        _order, visit = self._visit()
        self.assertFalse(visit._fs_record_position(23.5, 58.4), "draft visits take no position")
        visit.action_assign()
        self.assertFalse(visit._fs_record_position('x', None))
        self.assertFalse(visit._fs_record_position(0, 0))

        self.assertTrue(visit._fs_record_position(23.5, 58.4, accuracy=8, battery=0.7))
        self.assertEqual(len(visit.position_ids), 1)
        self.assertEqual(visit.tech_battery, 0.7)
        # ~10 m: the live point moves, the trail does not grow
        self.assertTrue(visit._fs_record_position(23.50009, 58.4))
        self.assertEqual(len(visit.position_ids), 1)
        self.assertAlmostEqual(visit.tech_lat, 23.50009, places=5)
        # ~110 m: a new trail point
        visit._fs_record_position(23.501, 58.4)
        self.assertEqual(len(visit.position_ids), 2)

    def test_distance_and_eta(self):
        _order, visit = self._visit()
        visit.action_assign()
        visit._fs_record_position(CUSTOMER[0], 58.35)       # 0.1° west, ~10.2 km
        visit.action_on_the_way()
        self.assertEqual((visit.start_lat, visit.start_lng), (CUSTOMER[0], 58.35))
        self.assertAlmostEqual(visit.distance_km, 10.2, delta=0.1)
        self.assertEqual(visit.eta_minutes, 21)            # 10.2 km at 30 km/h, rounded up
        self.assertTrue(visit.eta_at)
        self.assertFalse(visit.tech_stale)
        self.assertTrue(visit.directions_url)
        self.assertIn('openstreetmap', str(visit.tech_map_html))

    def test_tracking_block_shows_only_what_is_due(self):
        _order, visit = self._visit()
        self.assertEqual(self._track()['state'], 'draft')
        self.assertIsNone(self._track()['technician'])

        visit.action_assign()
        block = self._track()
        self.assertEqual(block['technician']['name'], 'Arjun Tech')
        self.assertEqual(block['technician']['phone'], '+96890000001')
        self.assertEqual(block['arrival_code'], visit.sudo().arrival_code)
        self.assertIsNone(block['live'])
        self.assertTrue(block['steps'][0]['current'])
        self.assertTrue(block['steps'][0]['at'].endswith('Z'))

        visit._fs_record_position(CUSTOMER[0], 58.35)
        visit.action_on_the_way()
        block = self._track()
        self.assertAlmostEqual(block['live']['lat'], CUSTOMER[0], places=5)
        self.assertEqual(block['dest'], {'lat': CUSTOMER[0], 'lng': CUSTOMER[1]})
        self.assertEqual(block['eta_minutes'], 21)

        visit._fs_arrive(skip_code=True)
        visit.action_done()
        block = self._track()
        self.assertEqual(block['state'], 'done')
        self.assertIsNone(block['live'])
        self.assertIsNone(block['arrival_code'])
        self.assertIsNone(block['technician']['phone'])
        self.assertTrue(all(step['done'] for step in block['steps']))

    def test_technician_page_link(self):
        _order, visit = self._visit()
        visit.action_assign()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        params = dict(part.split('=', 1) for part in link.split('&'))
        ref, token = visit.name, params['t']
        Visit = self.env['fix.service.visit']

        self.assertEqual(Visit.tech_page(HOST, ref, 'wrong')['error'], 'unknown')
        self.assertEqual(Visit.tech_page('other.example', ref, token)['error'], 'unknown')
        page = Visit.tech_page(HOST, ref, token)
        self.assertTrue(page['ok'])
        self.assertEqual(page['state'], 'assigned')
        self.assertEqual(page['customer']['address'], 'Villa 12')
        self.assertTrue(page['share'])
        self.assertNotIn('arrival_code', page)

        ping = Visit.tech_page(HOST, ref, token, action='ping', lat=CUSTOMER[0], lng=58.35, accuracy=9)
        self.assertTrue(ping['saved'])
        self.assertAlmostEqual(visit.tech_lng, 58.35, places=5)

        self.assertEqual(Visit.tech_page(HOST, ref, token, action='on_the_way')['state'], 'on_the_way')
        self.assertEqual(self._track()['eta_minutes'], 21)
        code = visit.sudo().arrival_code
        wrong = Visit.tech_page(HOST, ref, token, action='arrive', code='0000' if code != '0000' else '1111')
        self.assertFalse(wrong['ok'])
        self.assertEqual(wrong['error'], 'wrong_code')
        self.assertEqual(Visit.tech_page(HOST, ref, token, action='arrive', code=code)['state'], 'arrived')
        self.assertFalse(Visit.tech_page(HOST, ref, token, action='fly')['ok'])
        self.assertTrue(Visit.tech_page(HOST, ref, token, action='done', lat='x')['ok'])
        self.assertEqual(visit.state, 'done')
        self.assertFalse(Visit.tech_page(HOST, ref, token, action='ping', lat=23.5, lng=58.4)['saved'])

        # A new link stops the old one
        visit.state = 'in_progress'
        visit.action_send_tech_link()
        self.assertEqual(Visit.tech_page(HOST, ref, token)['error'], 'unknown')

    def test_job_card_moves_the_visit(self):
        order, visit = self._visit()
        visit.action_assign()
        category = self.env['device.category'].create({'name': 'FS Phones'})
        brand = self.env['device.brand'].create({'name': 'FS Brand', 'category_id': category.id})
        partner = order._find_or_create_partner()
        card = self.env['job.card'].create({
            'partner_id': partner.id, 'brand_id': brand.id, 'device_category_id': category.id,
            'assigned_to': self.employee.id, 'issue': 'Screen', 'delivery_type': 'door_step',
            'online_order_id': order.id,
        })
        self.assertEqual(visit.job_card_id, card)
        self.assertEqual(card.fs_visit_count, 1)
        card.write({'state': 'inspection'})
        self.assertEqual(visit.state, 'in_progress')
        self.assertTrue(visit.arrived_on)
        card.write({'state': 'completed'})
        self.assertEqual(visit.state, 'done')

    def test_technician_sees_only_own_visits(self):
        _order, visit = self._visit()
        Visit = self.env['fix.service.visit']
        self.assertIn(visit, Visit.with_user(self.tech_user).search([]))
        self.assertNotIn(visit, Visit.with_user(self.other_user).search([]))

    def test_pasted_map_link_sets_the_point(self):
        _order, visit = self._visit()
        visit.customer_map_link = 'https://www.google.com/maps/place/Qurum/@23.5812,58.3871,17z'
        self.assertAlmostEqual(visit.customer_lat, 23.5812, places=4)
        self.assertEqual(visit.customer_location_source, 'link')

    def test_geo_helpers(self):
        self.assertEqual(parse_map_link('https://maps.google.com/?q=23.58,58.38'), (23.58, 58.38))
        self.assertEqual(parse_map_link('https://maps.google.com/?q=23.58%2C58.38'), (23.58, 58.38))
        self.assertEqual(parse_map_link('...!3d23.61!4d58.54...@23.0,58.0,15z'), (23.61, 58.54))
        self.assertEqual(parse_map_link(' 23.5, 58.4 '), (23.5, 58.4))
        self.assertIsNone(parse_map_link('no place here'))
        self.assertAlmostEqual(metres(0, 0, 0, 1), 111195, delta=5)
