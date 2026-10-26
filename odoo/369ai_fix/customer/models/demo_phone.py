# -*- coding: utf-8 -*-
"""The demo number: a mobile number that signs in with a fixed code, for trying the website
(sign-in, Spin & Win, booking, My orders) without a phone. Test databases only.

It is on only when both system parameters are set (Settings > Technical > System Parameters):
``369ai_fix.demo_phone`` (E.164, e.g. +96891234567) and ``369ai_fix.demo_code`` (6 digits).
A live database never has them, so there it does nothing.

The number signs in to its own "Demo Customer" account (made the first time), already proven,
so no password is asked even when older test accounts carry the same number. No WhatsApp
message is sent, and other contacts with the number are not joined into it. 369 Mart's sign-in
is extended here, never changed.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

DEMO_PHONE_PARAM = '369ai_fix.demo_phone'
DEMO_CODE_PARAM = '369ai_fix.demo_code'
DEMO_LOGIN = 'demo-customer@369ai-fix.test'
DEMO_NAME = 'Demo Customer'


def _demo(env):
    """(phone, code) when the demo number is on, else (None, None)."""
    params = env['ir.config_parameter'].sudo()
    phone = (params.get_param(DEMO_PHONE_PARAM) or '').strip()
    code = (params.get_param(DEMO_CODE_PARAM) or '').strip()
    if not phone.startswith('+') or not (len(code) == 6 and code.isdigit()):
        return None, None
    return phone, code


class Mart369PhoneCode(models.Model):
    _inherit = 'mart369.phone.code'

    @api.model
    def _mart369_wait_minutes(self, phone, ip=None):
        if phone and phone == _demo(self.env)[0]:
            return 0            # anyone may try the demo, any number of times
        return super()._mart369_wait_minutes(phone, ip)

    @api.model
    def _mart369_issue(self, phone, purpose, user=None, ip=None):
        record, code = super()._mart369_issue(phone, purpose, user=user, ip=ip)
        demo_phone, demo_code = _demo(self.env)
        if phone and phone == demo_phone:
            record.sudo().code_hash = self._mart369_digest(phone, demo_code)
            code = demo_code
        return record, code


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _mart369_send_login_code(self, phone, code):
        if phone and phone == _demo(self.env)[0]:
            return 'sent'       # nothing goes out: the code is the fixed one
        return super()._mart369_send_login_code(phone, code)

    @api.model
    def _mart369_demo_user(self, phone):
        """The demo number's own account, made the first time, its number proven."""
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        user = Users.search([('login', '=', DEMO_LOGIN)], limit=1)
        if not user:
            user = Users._create_user_from_template({'login': DEMO_LOGIN, 'name': DEMO_NAME})
            _logger.info("369ai_fix: made the demo customer account for %s", phone)
        if not user.active:
            user.active = True
        partner = user.partner_id.sudo()
        if partner.phone != phone or not partner.mart369_phone_verified:
            partner.with_context(mart369_phone_proven=True).write({
                'phone': phone, 'mart369_phone_verified': True,
                'mart369_phone_verified_at': fields.Datetime.now(),
            })
        return user

    @api.model
    def _mart369_phone_owner(self, phone):
        if phone and phone == _demo(self.env)[0]:
            user = self._mart369_demo_user(phone)
            return user.partner_id, user
        return super()._mart369_phone_owner(phone)

    def _mart369_after_phone_verified(self):
        # the demo account never takes in the test contacts that share its number
        if self and self.env['res.users'].sudo().search_count(
                [('login', '=', DEMO_LOGIN), ('partner_id', '=', self.commercial_partner_id.id)]):
            return {'orders': 0, 'addresses': 0}
        return super()._mart369_after_phone_verified()
