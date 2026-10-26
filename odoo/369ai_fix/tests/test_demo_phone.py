# -*- coding: utf-8 -*-
"""The demo number (customer/models/demo_phone.py): off without its two system parameters;
on, it gets the fixed code, sends nothing, has no wait, and signs in to its own proven
"Demo Customer" account even when other accounts carry the same number."""
from odoo.tests import TransactionCase, tagged

from ..customer.models.demo_phone import DEMO_CODE_PARAM, DEMO_LOGIN, DEMO_PHONE_PARAM

DEMO = '+96899990001'


@tagged('post_install', '-at_install')
class TestDemoPhone(TransactionCase):

    def setUp(self):
        super().setUp()
        self.params = self.env['ir.config_parameter'].sudo()
        self.Code = self.env['mart369.phone.code'].sudo()
        self.Partner = self.env['res.partner'].sudo()
        # an older account with the same number and no proof (as on the test database)
        self.old = self.env['res.users'].sudo()._create_user_from_template(
            {'login': 'old-demo-owner@example.com', 'name': 'Old Owner'})
        self.old.partner_id.phone = DEMO

    def _on(self):
        self.params.set_param(DEMO_PHONE_PARAM, DEMO)
        self.params.set_param(DEMO_CODE_PARAM, '123456')

    def test_off_without_the_parameters(self):
        self.params.set_param(DEMO_PHONE_PARAM, False)
        self.params.set_param(DEMO_CODE_PARAM, '123456')
        record, code = self.Code._mart369_issue(DEMO, 'signin')
        self.assertEqual(record.code_hash, self.Code._mart369_digest(DEMO, code), 'a normal random code')
        partner, user = self.Partner._mart369_phone_owner(DEMO)
        self.assertEqual(user, self.old)
        self.assertFalse(self.env['res.users'].sudo().search([('login', '=', DEMO_LOGIN)]))

    def test_on_signs_in_its_own_account_with_the_fixed_code(self):
        self._on()
        self.assertEqual(self.Code._mart369_wait_minutes(DEMO, '1.2.3.4'), 0)
        record, code = self.Code._mart369_issue(DEMO, 'signin', ip='1.2.3.4')
        self.assertEqual(code, '123456')
        self.assertEqual(self.Partner._mart369_send_login_code(DEMO, code), 'sent')
        checked, why = self.Code._mart369_check(DEMO, 'signin', '123456')
        self.assertIsNone(why)
        self.assertEqual(checked, record)
        partner, user = self.Partner._mart369_phone_owner(DEMO)
        self.assertEqual(user.login, DEMO_LOGIN)
        self.assertTrue(partner.mart369_phone_verified, 'no password is asked')
        self.assertEqual(partner.phone, DEMO)
        self.assertEqual(partner._mart369_after_phone_verified(), {'orders': 0, 'addresses': 0})
        # the same account every time; another number keeps the normal owner
        self.assertEqual(self.Partner._mart369_phone_owner(DEMO)[1], user)
        self.assertFalse(self.Partner._mart369_phone_owner('+96899990002')[1])
