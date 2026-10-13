# -*- coding: utf-8 -*-
"""The sign-in code names the website the customer is on.

Customers of the repair site sign in with 369 Mart's accounts (mart369_auth). The
repair site's server marks its calls with the header ``X-Fix-Site: <host>``; when
that host is one of our Online Service websites the code says "Your Danat Fix code"
and goes out through that website's WhatsApp number. Anything else: 369 Mart's own
text, unchanged.
"""
import logging

from odoo import _, api, models
from odoo.http import request

_logger = logging.getLogger(__name__)


def _digits(number):
    return ''.join(c for c in (number or '') if c.isdigit())


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _mart369_send_login_code(self, phone, code):
        host = ''
        try:
            if request and request.httprequest:
                host = request.httprequest.headers.get('X-Fix-Site', '')
        except RuntimeError:     # no HTTP request (cron, shell)
            host = ''
        site = self.env['online.service.site'].sudo()._for_host(host) if host else None
        if not site:
            return super()._mart369_send_login_code(phone, code)
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
