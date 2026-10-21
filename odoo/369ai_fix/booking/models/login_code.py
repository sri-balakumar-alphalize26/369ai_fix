# -*- coding: utf-8 -*-
"""The sign-in code names the website the customer is on.

Customers of the repair site sign in with 369 Mart's accounts (mart369_auth). The
repair site's server marks its calls with the header ``X-Fix-Site: <host>``; when
that host is one of our Online Service websites the code says "Your Danat Fix code"
and goes out through that website's WhatsApp number. Anything else: 369 Mart's own
text, unchanged.

Test mode (local test databases only): when the system parameter
``369ai_fix.test_login_code`` holds 6 digits, every sign-in code asked for from our
repair site IS those digits and no WhatsApp is sent. 369 Mart's own sign-ins are
never affected. Leave the parameter unset on a real database.
"""
import logging

from odoo import _, api, models
from odoo.http import request

from ...customer.models.online_otp import TEST_CODE_PARAM, test_code as _test_code

_logger = logging.getLogger(__name__)


def _digits(number):
    return ''.join(c for c in (number or '') if c.isdigit())


def _fix_site(env):
    """The Online Service website this request came from (X-Fix-Site), or None."""
    host = ''
    try:
        if request and request.httprequest:
            host = request.httprequest.headers.get('X-Fix-Site', '')
    except RuntimeError:     # no HTTP request (cron, shell)
        host = ''
    return env['online.service.site'].sudo()._for_host(host) if host else None


class PhoneCode(models.Model):
    _inherit = 'mart369.phone.code'

    @api.model
    def _mart369_issue(self, phone, purpose, user=None, ip=None):
        record, code = super()._mart369_issue(phone, purpose, user=user, ip=ip)
        test = _test_code(self.env)
        if test and _fix_site(self.env):
            record.sudo().code_hash = self._mart369_digest(phone, test)
            return record, test
        return record, code


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _mart369_send_login_code(self, phone, code):
        site = _fix_site(self.env)
        if not site:
            return super()._mart369_send_login_code(phone, code)
        if _test_code(self.env):
            _logger.warning("369ai fix: TEST MODE - sign-in code for %s not sent (%s is set)",
                            phone, TEST_CODE_PARAM)
            return 'sent'
        session = site._wa_session()
        if not session and 'mart369.whatsapp' in self.env:
            session = self.env['mart369.whatsapp']._mart369_session()
        if not session:
            return 'none'
        body = _("Your %(site)s code is *%(code)s*\n\n"
                 "It expires in 10 minutes. Don't share it with anyone - "
                 "%(site)s will never ask you for it.", site=site.name, code=code)
        try:
            sent = session.send_message(_digits(phone), body)
        except Exception as err:  # noqa: BLE001
            if type(err).__name__ == 'WhatsAppQueued':
                return 'queued'
            _logger.exception('369ai fix: could not send a sign-in code to %s', phone)
            return 'offline'
        return 'sent' if sent else 'offline'
