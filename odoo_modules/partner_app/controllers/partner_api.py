"""The partner app's own routes, next to the delivery module's `/api/delivery/*`.

Signed in the same way: the bearer token from `/api/delivery/auth/verify-code`
(checked by the delivery module's own `sa.delivery.token._rider_from_token`),
or an Odoo session linked to the rider. No second login, and nothing here is
imported from the delivery module's controller, so a change there cannot
break these routes.
"""

import functools

from odoo import _, fields, http
from odoo.http import request


def _json(payload, status=200):
    return request.make_json_response(payload, status=status)


def _fail(message, status=400, **extra):
    out = {'success': False, 'message': message}
    out.update(extra)
    return _json(out, status=status)


def _rider_from_request():
    header = request.httprequest.headers.get('Authorization') or ''
    token = header[7:].strip() if header.lower().startswith('bearer ') else ''
    if token:
        rider = request.env['sa.delivery.token'].sudo()._rider_from_token(token)
        if rider:
            return rider
    if request.session.uid:
        return request.env['sa.delivery.partner'].sudo().search(
            [('user_id', '=', request.session.uid), ('active', '=', True)],
            limit=1)
    return request.env['sa.delivery.partner']


def authenticated(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        rider = _rider_from_request()
        if not rider:
            return _fail(_("Not signed in."), status=401, code='unauthorized')
        return func(self, rider, *args, **kwargs)
    return wrapper


class PartnerAppApi(http.Controller):

    @http.route('/api/partner/me', type='http', auth='public',
                methods=['GET'], csrf=False)
    @authenticated
    def me(self, rider, **kw):
        """Which lines this person works in, and whether they are busy.

        The app asks once after sign-in and again when it comes back to the
        front. A server without this module answers 404, which the app reads
        as "Delivery only".
        """
        out = {'success': True, 'rider_id': rider.id,
               'server_time': fields.Datetime.now().isoformat() + 'Z'}
        out.update(rider._partner_app_block())
        return _json(out)

    @http.route('/api/partner/country', type='http', auth='public',
                methods=['GET'], csrf=False)
    def country(self, **kw):
        """The country of the database's main company, for the sign-in screen.

        Asked before anyone signs in, as soon as a database is chosen, so the
        number field opens on the right dialling code. Nothing private: only
        the country. A company with no country answers nulls and the app
        keeps its own default.
        """
        company = request.env['res.company'].sudo().search([], order='id', limit=1)
        country = company.country_id
        return _json({
            'success': True,
            'country_code': country.code or None,
            'phone_code': country.phone_code or None,
            'name': country.name or None,
        })
