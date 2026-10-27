# -*- coding: utf-8 -*-
"""The green screens (app/models/fix_screen.py): every screen loads for the people who use
it, only the listed fields and buttons can be used, and the pop-ups run the wizards'
own buttons (approve / reject, the arrival code, Before you start, What did you find?)."""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..app.models.fix_screen_configs import SCREENS

HOST = 'screen-test.example'
PHONE = '+968 9123 7777'
CUSTOMER = (23.6, 58.45)


@tagged('post_install', '-at_install')
class TestScreens(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['online.service.site'].create({
            'name': 'Screen Test', 'domains': HOST, 'whatsapp_messages': True})
        cls.admin = new_test_user(
            cls.env, login='screen_admin',
            groups='base.group_user,base.group_system,mobile_repair.group_mobile_repair_manager,'
                   '369ai_fix.group_fix_website_editor,stock.group_stock_user')
        cls.recep = new_test_user(
            cls.env, login='screen_recep',
            groups='base.group_user,mobile_repair.group_mobile_repair_receptionist')
        cls.tech_user = new_test_user(cls.env, login='screen_tech', groups='base.group_user')
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Salim Tech', 'user_id': cls.tech_user.id, 'mobile_phone': '+96890000077'})
        cls.env.company.write({'fs_arrival_otp': True, 'fs_stale_after_s': 120})
        cls.Screen = cls.env['fix.screen']
        cls.Order = cls.env['online.service.order']

    def setUp(self):
        super().setUp()
        self.sent = []

        def fake_send(site, phone, text):
            self.sent.append((phone, text))
            return 'sent', ''

        self.startPatcher(patch.object(type(self.env['online.service.site']), '_wa_send', fake_send))
        self.startPatcher(patch.object(type(self.env['bus.bus']), '_sendone', lambda *a, **k: None))

    def _book(self, **extra):
        payload = {
            'host': HOST, 'mode': 'doorstep', 'name': 'Huda', 'phone': PHONE,
            'area': 'Qurum', 'address': 'Villa 3', 'lat': CUSTOMER[0], 'lng': CUSTOMER[1],
            'lines': [{'device': 'Mobile Phones', 'model': 'iPhone 13', 'issue': 'Screen', 'qty': 1}],
        }
        payload.update(extra)
        result = self.Order.website_create(payload)
        self.assertTrue(result['ok'], result)
        return self.Order.search([('name', '=', result['ref'])])

    def _card(self, order):
        """A job card for the booking (the database's catalogue may not match the test words)."""
        if order.job_card_ids:
            return order.job_card_ids[:1]
        brand = self.env['device.brand'].search([], limit=1) or self.env['device.brand'].create({'name': 'TestBrand'})
        card = self.env['job.card'].create({
            'partner_id': order._find_or_create_partner().id, 'phone': PHONE, 'brand_id': brand.id,
            'assigned_to': self.employee.id, 'issue': 'Screen', 'online_order_id': order.id,
            'delivery_type': 'door_step',
        })
        order.invalidate_recordset()      # job_card_count is not stored: read it again
        return card

    def _visit_on_the_way(self):
        order = self._book()
        order.action_confirm()
        order.with_user(self.recep).fix_desk_act('assign', stage='to_assign', technician_id=self.employee.id)
        visit = order.visit_ids
        visit.action_on_the_way()
        return order, visit

    # ------------------------------------------------------------------ every screen
    def test_every_screen_loads(self):
        Screen = self.Screen.with_user(self.admin)
        for key, cfg in SCREENS.items():
            if cfg['model'] not in self.env:
                continue
            meta = Screen.screen_meta(key)
            self.assertEqual(meta['key'], key)
            self.assertTrue(meta['title'])
            for column in meta['columns']:
                self.assertIn(column, meta['fields'], '%s: column %s' % (key, column))
            if meta['kind'] == 'settings':
                self.assertIn('values', Screen.screen_record(key, 0))
            elif meta['kind'] == 'single':
                Screen.screen_record(key, Screen.screen_single(key))
            else:
                for f in cfg.get('filters') or [{'key': None}]:
                    data = Screen.screen_list(key, filter=f['key'])
                    self.assertIn('rows', data, key)
                if data['rows']:
                    Screen.screen_record(key, data['rows'][0]['id'])
                for mode in meta['modes']:
                    Screen.screen_list(key, mode=mode)

    def test_the_desk_staff_see_their_screens(self):
        Screen = self.Screen.with_user(self.recep)
        for key in ('bookings', 'job_cards', 'visits', 'spare_requests', 'services', 'spare_parts', 'categories'):
            Screen.screen_meta(key)
            Screen.screen_list(key)
        with self.assertRaises(AccessError):
            Screen.screen_meta('repair_settings')          # admins only
        with self.assertRaises(AccessError):
            Screen.screen_meta('slots')                    # managers only
        with self.assertRaises(AccessError):
            Screen.screen_meta('labour_prices')            # managers only

    def test_create_job_card_opens_the_green_screen(self):
        order = self._book()
        outcome = self.Screen.with_user(self.admin).screen_button('bookings', order.id, 'action_create_job_card')
        self.assertEqual(outcome['open']['screen'], 'job_cards')
        self.assertTrue(outcome['open']['new'])
        self.assertEqual(outcome['open']['defaults']['online_order_id'][0], order.id)

    def test_secrets_never_leave(self):
        order = self._book()
        meta = self.Screen.screen_meta('bookings')
        self.assertNotIn('upload_token_hash', meta['fields'])
        record = self.Screen.screen_record('bookings', order.id)
        self.assertNotIn('upload_token_hash', record['values'])
        self.assertNotIn('slot_token_hash', record['values'])

    def test_only_listed_fields_and_buttons(self):
        order = self._book()
        Screen = self.Screen.with_user(self.recep)
        record = Screen.screen_save('bookings', order.id, {'area': 'Ruwi'})
        self.assertEqual(order.area, 'Ruwi')
        self.assertEqual(record['values']['area'], 'Ruwi')
        with self.assertRaises(AccessError):
            Screen.screen_save('bookings', order.id, {'web_ref': 'X1'})      # shown, not changed here
        with self.assertRaises(AccessError):
            Screen.screen_save('bookings', order.id, {'upload_token_hash': 'x'})
        with self.assertRaises(AccessError):
            Screen.screen_button('bookings', order.id, 'unlink')
        order.action_confirm()
        with self.assertRaises(UserError):
            Screen.screen_button('bookings', order.id, 'action_wb_approve')  # only for a new booking
        self.assertNotIn('action_wb_approve', Screen.screen_record('bookings', order.id)['buttons'])

    def test_filters(self):
        order = self._book()
        ids = lambda f: [r['id'] for r in self.Screen.screen_list('bookings', filter=f, query='Huda')['rows']]  # noqa: E731
        self.assertIn(order.id, ids('new'))
        self.assertIn(order.id, ids('open'))
        self.assertNotIn(order.id, ids('done'))
        self.assertNotIn(order.id, ids('rejected_today'))

    # ------------------------------------------------------------------ pop-ups
    def test_reject_through_the_green_popup(self):
        order = self._book()
        Screen = self.Screen.with_user(self.recep)
        # from the desk: the desk's wizard action becomes a green pop-up
        action = order.with_user(self.recep).fix_desk_act('reject')['action']
        popup = Screen.screen_popup_open(action)['popup']
        self.assertEqual(popup['model'], 'wb.reject.wizard')
        self.assertIn('reason', popup['fields'])
        with self.assertRaises(AccessError):
            Screen.screen_popup_submit('wb.reject.wizard', False, {'reason': 'x'}, 'unlink', popup['context'])
        outcome = Screen.screen_popup_submit('wb.reject.wizard', False, {'reason': 'No parts for this model'},
                                             'action_confirm', popup['context'])
        self.assertTrue(outcome.get('done'), outcome)
        self.assertEqual(order.state, 'cancelled')
        self.assertTrue(order.rejected)
        self.assertEqual(order.reject_reason, 'No parts for this model')

    def test_approve_is_a_green_popup(self):
        order = self._book()
        action = order.with_user(self.recep).fix_desk_act('approve')['action']
        outcome = self.Screen.with_user(self.recep).screen_popup_open(action)
        self.assertEqual(outcome['popup']['model'], 'wb.approve.wizard')
        self.assertEqual(outcome['popup']['context'].get('default_order_id'), order.id)
        self.assertIn('parts_html', outcome['popup']['values'])
        # no parts yet is normal (the technician picks them at the visit): no "No spare parts" line
        self.assertFalse(outcome['popup']['values']['parts_html'])

    def test_arrival_code_wrong_then_right(self):
        _order, visit = self._visit_on_the_way()
        Screen = self.Screen.with_user(self.recep)
        popup = Screen.screen_button('visits', visit.id, 'action_arrived')['popup']
        self.assertEqual(popup['model'], 'fix.service.visit.arrival')
        code = visit.sudo().arrival_code
        wrong = '0000' if code != '0000' else '1111'
        again = Screen.screen_popup_submit(popup['model'], False, {'code': wrong}, 'action_confirm', popup['context'])
        self.assertTrue(again['popup']['res_id'])          # the same window, with the message
        self.assertTrue(again['popup']['values']['message'])
        self.assertEqual(visit.state, 'on_the_way')
        self.assertEqual(visit.sudo().arrival_tries, 1)  # kept: a wrong code does not roll back
        done = Screen.screen_popup_submit(popup['model'], again['popup']['res_id'], {'code': code},
                                          'action_confirm', again['popup']['context'])
        self.assertTrue(done.get('done'), done)
        self.assertEqual(visit.state, 'arrived')

    def test_before_you_start_and_what_did_you_find(self):
        _order, visit = self._visit_on_the_way()
        visit._fs_arrive(skip_code=True)
        Screen = self.Screen.with_user(self.recep)
        popup = Screen.screen_button('visits', visit.id, 'action_start')['popup']
        self.assertEqual(popup['kind'], 'checks')
        checks = Screen.screen_checks(visit.id)
        self.assertTrue(checks['view']['safety'])
        self.assertTrue(checks['view']['missing'])
        line = checks['view']['safety'][0]
        checks = Screen.screen_checks(visit.id, 'check_tick', {'item_id': line['id'], 'done': True})
        self.assertTrue(next(s for s in checks['view']['safety'] if s['id'] == line['id'])['done'])
        with self.assertRaises(UserError):
            Screen.screen_checks(visit.id, 'start')          # photos and video still missing
        self.assertEqual(visit.state, 'arrived')

        visit.with_context(fix_checks_passed=True).action_start()
        popup = Screen.screen_button('visits', visit.id, 'action_open_result')['popup']
        self.assertEqual(popup['kind'], 'result')
        result = Screen.screen_result(visit.id)
        self.assertEqual(result['view']['stage'], 'find')
        result = Screen.screen_result(visit.id, 'result_fixed', {'note': 'Loose cable, fixed'})
        self.assertFalse(result['message'], result)
        # repaired: the visit stays open to finish (after photo, payment, the customer's code)
        self.assertEqual(visit.close_stage, 'finish')
        self.assertEqual(visit.state, 'in_progress')

    # ------------------------------------------------------------------ lines, tables, settings
    def test_job_card_line_takes_the_price(self):
        order = self._book()
        card = self._card(order)
        service = self.env['product.product'].create({'name': 'Screen fit', 'type': 'service', 'lst_price': 12.5})
        before = len(card.service_line_ids)
        record = self.Screen.with_user(self.admin).screen_line(
            'job_cards', card.id, 'service_line_ids', 'add', values={'product_id': service.id})
        self.assertEqual(len(card.service_line_ids), before + 1)
        line = card.service_line_ids.filtered(lambda l: l.product_id == service)
        self.assertEqual(line.unit_price, 12.5)
        self.assertTrue(any(l['id'] == line.id for l in record['lines']['service_line_ids']))
        with self.assertRaises(AccessError):
            self.Screen.with_user(self.admin).screen_line(
                'job_cards', card.id, 'service_line_ids', 'update', line.id, {'tax_ids': []})

    def test_tables_edit_in_the_row(self):
        Screen = self.Screen.with_user(self.admin)
        rec = Screen.screen_save('accessories', False, {'name': 'Stylus pen test'})
        accessory = self.env['device.accessory'].browse(rec['id'])
        self.assertEqual(accessory.name, 'Stylus pen test')
        Screen.screen_save('accessories', accessory.id, {'active': False})
        self.assertFalse(accessory.active)
        items = self.env['fix.safety.item'].search([], limit=2)
        if len(items) == 2:
            Screen.screen_resequence('safety_items', list(reversed(items.ids)))
            self.assertLess(items[1].sequence, items[0].sequence)

    def test_repair_settings_save(self):
        Screen = self.Screen.with_user(self.admin)
        record = Screen.screen_save('repair_settings', 0, {'wb_slot_days': 9})
        self.assertEqual(self.env.company.wb_slot_days, 9)
        self.assertEqual(record['values']['wb_slot_days'], 9)

    def test_notes(self):
        order = self._book()
        notes = self.Screen.with_user(self.recep).screen_note('bookings', order.id, 'Customer asked for evening')
        self.assertTrue(any('evening' in n['body'] for n in notes))
        merged = self.Screen.with_user(self.recep).screen_notes([['bookings', order.id]])
        self.assertTrue(any('evening' in n['body'] for n in merged))
