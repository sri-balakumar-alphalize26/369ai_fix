# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_visit import HOST, DoorstepCase

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64
b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731


@tagged('post_install', '-at_install')
class TestVisitChecks(DoorstepCase):
    """Safety check, device photos and video before work starts."""

    def _arrived(self):
        _order, visit = self._visit()
        visit.action_assign()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        token = dict(part.split('=', 1) for part in link.split('&'))['t']
        visit.action_on_the_way()
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        return visit, token

    def _fill(self, visit):
        visit._vc_prepare()
        visit.safety_line_ids.write({'worn': True})
        self.env['fix.visit.check.photo'].create({'visit_id': visit.id, 'kind': 'safety', 'image': b64(PNG)})
        visit.device_photo_ids.write({'image': b64(PNG)})
        visit.device_video = b64(MP4)

    def test_start_opens_the_window_until_done(self):
        visit, _token = self._arrived()
        action = visit.action_start()
        self.assertEqual(action['res_model'], 'fix.service.visit')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(visit.state, 'arrived')
        missing = visit._vc_missing()
        self.assertIn('Gloves not ticked', missing)
        self.assertIn('Front photo missing', missing)
        self.assertIn('Video missing', missing)
        self.assertEqual(len(visit.safety_line_ids), 5)
        self.assertEqual(len(visit.device_photo_ids), 6)
        with self.assertRaises(UserError):
            visit.action_start_checked()

        self._fill(visit)
        self.assertTrue(visit.checks_done)
        visit.action_start_checked()
        self.assertEqual(visit.state, 'in_progress')
        self.assertTrue(visit.checks_done_on)

    def test_optional_items_and_new_items(self):
        visit, _token = self._arrived()
        self._fill(visit)
        self.env.ref('369ai_fix.safety_item_shoe_covers').required = False
        visit.safety_line_ids.filtered(lambda l: l.name == 'Shoe covers').worn = False
        self.assertTrue(visit.checks_done)
        extra = self.env['fix.safety.item'].create({'name': 'Helmet'})
        self.assertIn('Helmet not ticked', visit._vc_missing())
        visit._vc_prepare()
        self.assertIn(extra, visit.safety_line_ids.item_id)

    def test_technician_page(self):
        visit, token = self._arrived()
        Visit = self.env['fix.service.visit']
        page = Visit.tech_page(HOST, visit.name, token)
        checks = page['checks']
        self.assertEqual(len(checks['safety']), 5)
        self.assertEqual(len(checks['sides']), 6)
        self.assertFalse(checks['video'])

        refused = Visit.tech_page(HOST, visit.name, token, action='start')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error'], 'checks')
        self.assertEqual(visit.state, 'arrived')

        for item in checks['safety']:
            Visit.tech_page(HOST, visit.name, token, action='check_tick', item_id=item['id'], done=True)
        bad = Visit.tech_page(HOST, visit.name, token, action='check_safety_photo', data=b64(b'not a photo'))
        self.assertEqual(bad['error'], 'check')
        for _i in range(3):
            self.assertTrue(Visit.tech_page(HOST, visit.name, token, action='check_safety_photo', data=b64(PNG))['ok'])
        fourth = Visit.tech_page(HOST, visit.name, token, action='check_safety_photo', data=b64(PNG))
        self.assertFalse(fourth['ok'])
        self.assertEqual(fourth['checks']['safety_photos'], 3)
        for side in checks['sides']:
            Visit.tech_page(HOST, visit.name, token, action='check_side_photo', photo_id=side['id'], data=b64(PNG))
        # a retake replaces the photo
        Visit.tech_page(HOST, visit.name, token, action='check_side_photo', photo_id=checks['sides'][0]['id'], data=b64(PNG))
        self.assertEqual(len(visit.device_photo_ids), 6)
        self.assertFalse(Visit.tech_page(HOST, visit.name, token, action='check_video', data=b64(PNG))['ok'])
        page = Visit.tech_page(HOST, visit.name, token, action='check_video', data=b64(MP4), name='clip.mp4')
        self.assertEqual(page['checks']['missing'], [])

        started = Visit.tech_page(HOST, visit.name, token, action='start')
        self.assertTrue(started['ok'])
        self.assertEqual(visit.state, 'in_progress')
        self.assertNotIn('checks', started)
        # after the start the checks cannot be changed from the phone
        late = Visit.tech_page(HOST, visit.name, token, action='check_clear_safety')
        self.assertEqual(late['error'], 'check')
        self.assertEqual(len(visit.safety_photo_ids), 3)

    def test_manager_can_start_without_checks(self):
        visit, _token = self._arrived()
        clerk = new_test_user(self.env, login='fs_clerk', groups='base.group_user,mobile_repair.group_mobile_repair_receptionist')
        with self.assertRaises(AccessError):
            visit.with_user(clerk).action_start_without_checks()
        boss = new_test_user(self.env, login='fs_boss', groups='base.group_user,mobile_repair.group_mobile_repair_manager')
        with self.assertRaises(UserError):
            visit.with_user(boss).action_start_without_checks()
        visit.checks_override_reason = 'Customer in a hurry'
        visit.with_user(boss).action_start_without_checks()
        self.assertEqual(visit.state, 'in_progress')
        self.assertEqual(visit.checks_override_by_id, boss)
        self.assertTrue(visit.message_ids.filtered(lambda m: 'Customer in a hurry' in (m.body or '')))

    def test_start_diagnosis_on_the_job_card_waits_for_the_checks(self):
        visit, _token = self._arrived()
        order = visit.order_id
        category = self.env['device.category'].create({'name': 'FS Phones'})
        brand = self.env['device.brand'].create({'name': 'FS Brand', 'category_id': category.id})
        card = self.env['job.card'].create({
            'partner_id': order._find_or_create_partner().id, 'brand_id': brand.id,
            'device_category_id': category.id, 'assigned_to': self.employee.id, 'issue': 'Screen',
            'delivery_type': 'door_step', 'online_order_id': order.id,
        })
        visit.job_card_id = card
        action = card.action_start_inspection()
        self.assertEqual(action['res_id'], visit.id)
        self.assertNotEqual(card.state, 'inspection')
        self._fill(visit)
        card.action_start_inspection()
        self.assertEqual(card.state, 'inspection')
        self.assertEqual(visit.state, 'in_progress')


    def test_start_work_starts_the_diagnosis_and_tells_the_customer(self):
        """Start work = Start diagnosis: the card goes to Inspection, the customer hears it with
        the safety check, and My orders shows the check with the technician's photo."""
        self.env['online.service.message'].search([('key', '=', 'inspection')]).body = \
            "Hi {name}, our technician is inspecting your device (order {order}).{safety}\nTrack it: {track_url}"
        visit, _token = self._arrived()
        order = visit.order_id
        category = self.env['device.category'].create({'name': 'FS Phones'})
        brand = self.env['device.brand'].create({'name': 'FS Brand', 'category_id': category.id})
        card = self.env['job.card'].create({
            'partner_id': order._find_or_create_partner().id, 'brand_id': brand.id,
            'device_category_id': category.id, 'assigned_to': self.employee.id, 'issue': 'Screen',
            'delivery_type': 'door_step', 'online_order_id': order.id,
        })
        visit.job_card_id = card
        self.assertEqual(card.state, 'draft')
        self._fill(visit)
        before = len(self.sent)
        visit.action_start_checked()
        self.assertEqual((visit.state, card.state), ('in_progress', 'inspection'))
        texts = [text for _phone, text in self.sent[before:] if 'inspecting your device' in text]
        self.assertEqual(len(texts), 1, self.sent[before:])
        self.assertIn('Safety check done', texts[0])
        self.assertIn('Gloves', texts[0])
        self.assertNotIn('{safety}', texts[0])
        safety = self._track()['safety']
        self.assertIn('Gloves', safety['items'])
        self.assertTrue(safety['photo'].startswith('data:image/'))

    def test_without_the_checks_no_safety_line(self):
        self.env['online.service.message'].search([('key', '=', 'inspection')]).body = \
            "Hi {name}, inspecting (order {order}).{safety}\nTrack it: {track_url}"
        visit, _token = self._arrived()
        order = visit.order_id
        before = len(self.sent)
        order.with_context(osm_extra={})._notify_customer('inspection')
        text = [t for _p, t in self.sent[before:]][-1]
        self.assertNotIn('Safety check', text)
        self.assertNotIn('{safety}', text)
        self.assertNotIn('safety', self._track())

    def test_start_diagnosis_waits_for_the_technician_at_the_door(self):
        """Pressing Start diagnosis before the technician is there: refused, no check skipped."""
        order, visit = self._visit()
        category = self.env['device.category'].create({'name': 'FS Tablets'})
        brand = self.env['device.brand'].create({'name': 'FS Tab Brand', 'category_id': category.id})
        card = self.env['job.card'].create({
            'partner_id': order._find_or_create_partner().id, 'brand_id': brand.id,
            'device_category_id': category.id, 'assigned_to': self.employee.id, 'issue': 'Screen',
            'delivery_type': 'door_step', 'online_order_id': order.id,
        })
        visit.job_card_id = card
        self.assertEqual(visit.state, 'draft')
        with self.assertRaises(UserError):
            card.action_start_inspection()                     # visit not even assigned
        visit.action_assign()
        visit.action_on_the_way()
        with self.assertRaises(UserError):
            card.action_start_inspection()                     # on the way
        self.assertEqual(card.state, 'draft')
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        self.assertEqual(card.action_start_inspection()['res_id'], visit.id)   # the safety check opens
        # no open visit (e.g. the device is at the office): starts as before
        office = self.env['job.card'].create({
            'partner_id': order._find_or_create_partner().id, 'brand_id': brand.id,
            'device_category_id': category.id, 'assigned_to': self.employee.id, 'issue': 'Battery',
            'delivery_type': 'door_step',
        })
        office.action_start_inspection()
        self.assertEqual(office.state, 'inspection')
