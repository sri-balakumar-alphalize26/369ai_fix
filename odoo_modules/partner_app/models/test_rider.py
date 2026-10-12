"""Test riders: made-up numbers that can still sign in to the app.

A rider ticked **Test rider** signs in with the fixed code `TEST_RIDER_CODE`
instead of a random one, and nothing is ever sent on WhatsApp to their
number: not the code, not a job message. A made-up number may well be a
stranger's real one.

The delivery module's own sign-in route is used unchanged - only the code it
issues and the message it would send are different.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)

TEST_RIDER_CODE = '111111'


class SaDeliveryLoginCode(models.Model):
    _inherit = 'sa.delivery.login.code'

    def _issue(self, rider):
        code = super()._issue(rider)
        if not rider.is_test_rider:
            return code
        row = self.sudo().search([('partner_id', '=', rider.id)],
                                 order='id desc', limit=1)
        row.code_hash = self.env['sa.delivery.token']._hash(
            '%s|%s' % (rider.id, TEST_RIDER_CODE))
        _logger.info("Partner app: test rider %s gets the fixed sign-in code",
                     rider.phone)
        return TEST_RIDER_CODE


class WhatsappSession(models.Model):
    _inherit = 'whatsapp.session'

    def send_message(self, phone, message):
        """Nothing goes to a test rider's number. False, as for a blocked send."""
        rider = self.env['sa.delivery.partner']._partner_app_test_rider_for(phone)
        if rider:
            _logger.info("Partner app: WhatsApp to test rider %s not sent",
                         rider.phone)
            return False
        return super().send_message(phone, message)
