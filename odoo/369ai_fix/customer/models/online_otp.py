# -*- coding: utf-8 -*-
"""Login codes for the website's "My orders" page, sent on WhatsApp.

Only a hash of the code is stored. A code lives 5 minutes and allows 5 tries;
one phone gets at most 3 codes per 15 minutes and one IP at most 10, so the
page cannot be used to spam people from the shop's WhatsApp number. A code is
only sent to a number that has ordered on that website.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

from .online_order import digits_of, clip

_logger = logging.getLogger(__name__)

CODE_MINUTES = 5
MAX_TRIES = 5
MAX_PER_PHONE = 3
MAX_PER_IP = 10
WINDOW_MINUTES = 15
# Test mode (local test databases only), shared with the booking sign-in (booking/login_code.py):
# when this system parameter holds 6 digits, every code IS those digits and no WhatsApp is sent.
TEST_CODE_PARAM = '369ai_fix.test_login_code'


def test_code(env):
    code = (env['ir.config_parameter'].sudo().get_param(TEST_CODE_PARAM) or '').strip()
    return code if len(code) == 6 and code.isdigit() else ''


class OnlineServiceOtp(models.Model):
    _name = 'online.service.otp'
    _description = 'Online Service Login Code'
    _order = 'id desc'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade', index=True)
    phone_digits = fields.Char(required=True, index=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    tries = fields.Integer(default=0)
    used = fields.Boolean(default=False)
    ip = fields.Char()

    @api.model
    def _hash(self, site_id, digits, code):
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret') or ''
        msg = ('%s:%s:%s' % (site_id, digits, code)).encode()
        return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    @api.model
    def otp_request(self, host, phone, ip=''):
        """Send a 6-digit code on WhatsApp. Always answers the same way whether the
        number has orders or not, so the page does not reveal who booked."""
        self.env['online.service.order']._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        digits = digits_of(phone)
        if not site:
            return {'ok': False, 'error': 'unknown website'}
        if not 7 <= len(digits) <= 15:
            return {'ok': False, 'error': 'bad phone'}
        Otp = self.sudo()
        since = fields.Datetime.now() - timedelta(minutes=WINDOW_MINUTES)
        ip = clip(ip, 64)
        if Otp.search_count([('phone_digits', '=', digits), ('create_date', '>=', since)]) >= MAX_PER_PHONE \
                or (ip and Otp.search_count([('ip', '=', ip), ('create_date', '>=', since)]) >= MAX_PER_IP):
            return {'ok': False, 'error': 'too many'}
        has_orders = self.env['online.service.order'].sudo().search_count(
            [('site_id', '=', site.id), ('phone_digits', '=', digits)], limit=1)
        if not has_orders:
            # Same answer as a real send; nothing goes out.
            return {'ok': True, 'sent': False}
        test = test_code(self.env)
        code = test or '%06d' % secrets.randbelow(1000000)
        Otp.search([('site_id', '=', site.id), ('phone_digits', '=', digits), ('used', '=', False)]) \
            .write({'used': True})
        Otp.create({
            'site_id': site.id,
            'phone_digits': digits,
            'code_hash': self._hash(site.id, digits, code),
            'expires_at': fields.Datetime.now() + timedelta(minutes=CODE_MINUTES),
            'ip': ip,
        })
        if test:
            _logger.warning("369ai fix: TEST MODE - My orders code for %s not sent (%s is set)",
                            digits, TEST_CODE_PARAM)
            return {'ok': True, 'sent': True, 'error': ''}
        text = _("Your %(site)s code is %(code)s\nIt is valid for %(minutes)s minutes. "
                 "Do not share it with anyone.",
                 site=site.name, code=code, minutes=CODE_MINUTES)
        status, _detail = site._wa_send(digits, text)
        return {'ok': status in ('sent', 'queued'), 'sent': status in ('sent', 'queued'),
                'error': '' if status in ('sent', 'queued') else 'whatsapp'}

    @api.model
    def otp_verify(self, host, phone, code):
        self.env['online.service.order']._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        digits = digits_of(phone)
        code = digits_of(code)
        if not site or not digits or len(code) != 6:
            return {'ok': False, 'error': 'bad code'}
        otp = self.sudo().search([
            ('site_id', '=', site.id), ('phone_digits', '=', digits), ('used', '=', False),
            ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
        if not otp:
            return {'ok': False, 'error': 'expired'}
        if otp.tries >= MAX_TRIES:
            otp.used = True
            return {'ok': False, 'error': 'locked'}
        otp.tries += 1
        if not hmac.compare_digest(otp.code_hash, self._hash(site.id, digits, code)):
            if otp.tries >= MAX_TRIES:
                otp.used = True
                return {'ok': False, 'error': 'locked'}
            return {'ok': False, 'error': 'bad code', 'left': MAX_TRIES - otp.tries}
        otp.used = True
        return {'ok': True}

    @api.autovacuum
    def _gc_old_codes(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=2))]).unlink()
