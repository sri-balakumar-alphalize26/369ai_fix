# -*- coding: utf-8 -*-
"""Oman postal codes in the shared address form, the way 369 Mart does Indian pincodes.

369 Mart's ``/369mart/pincode/<pin>`` asks ``res.partner._mart369_pincode_lookup``, which
knows India Post only. Here a 3-digit code is an Oman postal code: the wilayat (town), the
governorate (state) and an area come from OpenStreetMap (Nominatim, in English), and each
answer is kept like 369 Mart keeps its pincodes. Every other pincode goes to 369 Mart's own
lookup, unchanged. The answer has the same shape, plus the code's map point (lat/lng).
"""
import json
import logging
import re
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

_NOMINATIM = 'https://nominatim.openstreetmap.org/search'
_last_call = [0.0]          # Nominatim allows one request a second


def _clean(name):
    """'Bawshar Province' -> 'Bawshar', 'Muscat Governorate' -> 'Muscat', 'Wilayat Seeb' -> 'Seeb'."""
    name = re.sub(r'^(Wilayat|Wilayah)\s+', '', (name or '').strip(), flags=re.I)
    return re.sub(r'\s+(Province|Governorate)$', '', name, flags=re.I).strip()


def _plain(name):
    return re.sub(r'[^a-z]', '', (name or '').lower())


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _mart369_pincode_lookup(self, pin):
        if not re.fullmatch(r'\d{3}', pin or ''):
            return super()._mart369_pincode_lookup(pin)
        oman = self.env['res.country'].search([('code', '=', 'OM')], limit=1)
        if not oman:
            return {'ok': False}
        key = '369ai_fix.pc.om.%s' % pin
        params = self.env['ir.config_parameter'].sudo()
        cached = params.get_param(key)
        if cached:
            return json.loads(cached)
        wait = 1.1 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            reply = requests.get(_NOMINATIM, timeout=6, params={
                'postalcode': pin, 'countrycodes': 'om', 'format': 'jsonv2',
                'addressdetails': 1, 'limit': 1, 'accept-language': 'en',
            }, headers={'User-Agent': '369 ai Fix address form (%s)' % (self.env.company.email or 'odoo')})
            reply.raise_for_status()
            rows = reply.json() or []
        except Exception as exc:  # noqa: BLE001 - offline or slow: the form stays manual
            _logger.info('Oman postal code lookup failed for %s: %s', pin, exc)
            return {'ok': False}
        if not rows:
            return {'ok': False}
        row, address = rows[0], rows[0].get('address') or {}
        state_name = _clean(address.get('state'))
        state = oman.state_ids.filtered(
            lambda s: state_name and (_plain(s.name) in _plain(state_name) or _plain(state_name) in _plain(s.name)))[:1]
        area = _clean(address.get('suburb') or address.get('town') or address.get('village')
                      or address.get('neighbourhood'))
        payload = {
            'ok': True,
            'pin': pin,
            'town': _clean(address.get('county') or address.get('city') or address.get('province')
                           or address.get('municipality')),
            'state_id': state.id or False,
            'state': state.name or state_name,
            'areas': [area] if area else [],
            'lat': float(row.get('lat') or 0) or False,
            'lng': float(row.get('lon') or 0) or False,
        }
        params.set_param(key, json.dumps(payload))
        return payload
