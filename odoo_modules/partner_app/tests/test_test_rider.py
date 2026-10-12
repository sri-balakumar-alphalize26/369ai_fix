import json

from odoo.tests import HttpCase, tagged

from ..models.test_rider import TEST_RIDER_CODE


@tagged('post_install', '-at_install')
class TestTestRider(HttpCase):
    """A ticked Test rider signs in with the fixed code; nobody else can."""

    def setUp(self):
        super().setUp()
        Rider = self.env['sa.delivery.partner'].sudo()
        self.tester = Rider.create({
            'name': 'Made-up Rider', 'phone': '96891230001', 'kind': 'own',
            'work_type': 'both', 'is_test_rider': True})
        self.real = Rider.create({
            'name': 'Real Rider', 'phone': '96891230002', 'kind': 'own'})

    def _post(self, path, body):
        return self.url_open(
            '/api/delivery/auth/%s' % path, data=json.dumps(body),
            headers={'Content-Type': 'application/json'})

    def _sign_in(self, mobile, code):
        self.assertEqual(self._post('request-code', {'mobile': mobile}).status_code, 200)
        return self._post('verify-code', {'mobile': mobile, 'code': code})

    def test_test_rider_signs_in_with_the_fixed_code(self):
        res = self._sign_in('+96891230001', TEST_RIDER_CODE)
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.content)
        self.assertTrue(body['token'])
        self.assertEqual(body['rider']['id'], self.tester.id)

    def test_test_rider_refuses_another_code(self):
        res = self._sign_in('+96891230001', '654321')
        self.assertEqual(res.status_code, 401)

    def test_real_rider_does_not_get_the_fixed_code(self):
        res = self._sign_in('+96891230002', TEST_RIDER_CODE)
        self.assertEqual(res.status_code, 401)

    def test_test_rider_previews_service(self):
        block = self.tester._partner_app_block()
        self.assertEqual(block['lines'], ['delivery', 'service'])
        self.assertTrue(block['service_preview'])
        self.tester.work_type = 'service'
        self.assertEqual(self.tester._partner_app_block()['lines'], ['service'])

    def test_real_rider_gets_no_preview(self):
        self.real.work_type = 'both'
        block = self.real._partner_app_block()
        self.assertEqual(block['lines'], ['delivery'])
        self.assertFalse(block['service_preview'])

    def test_no_whatsapp_to_a_test_rider(self):
        Session = self.env['whatsapp.session']
        self.assertFalse(Session.browse().send_message('+968 9123 0001', 'hello'))
        Rider = self.env['sa.delivery.partner']
        self.assertEqual(Rider._partner_app_test_rider_for('0096891230001'), self.tester)
        self.assertFalse(Rider._partner_app_test_rider_for('96891230002'))
