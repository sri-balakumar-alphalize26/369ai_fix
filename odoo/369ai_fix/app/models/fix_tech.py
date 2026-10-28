# -*- coding: utf-8 -*-
"""My Visits: the technician's own screen in Odoo (static/src/app/tech/).

The same steps as the technician's web page from WhatsApp (visits/: `_fs_tech_do`), reached
with the technician's own Odoo login instead of the link. A technician sees and changes only
the visits they are the technician of (their employee is linked to their user); a repair
manager can open any visit, to help or to test. Office staff keep the Booking Desk.
"""
import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.image import image_process
from odoo.tools.mimetypes import guess_mimetype

from ...visits.models.geo import osm_embed
from ...visits.models.service_visit import OPEN_STATES, STATES, _iso

MANAGER = 'mobile_repair.group_mobile_repair_manager'
# only these keys of the caller's context reach the steps: a client cannot pass flags such
# as fix_checks_passed or wb_silent through My Visits
KEEP_CONTEXT = ('lang', 'tz', 'allowed_company_ids')
SEARCH_LIMIT = 50       # the search box lists the newest this many (and says how many matched)
CANCELLED_DAYS = 7      # visits the office cancelled stay in the list this long


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    @api.model
    def _fix_tech_me(self):
        return self.env['hr.employee'].sudo().search([('user_id', '=', self.env.uid)])

    @api.model
    def fix_tech_load(self):
        """My visits: the open ones (the soonest first), the ones finished today, and the ones
        the office cancelled in the last week (so the technician knows). A repair manager
        without an employee of their own sees every technician's."""
        me = self._fix_tech_me()
        manager = self.env.user.has_group(MANAGER)
        if not me and not manager:
            return {'visits': [], 'linked': False, 'manager': False, 'me': self.env.user.name}
        mine = [('technician_id', 'in', me.ids)] if me else []
        Visit = self.sudo()
        today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        visits = Visit.search(mine + [('state', 'in', OPEN_STATES)], order='slot_start asc, id asc', limit=100)
        done = Visit.search(mine + [('state', '=', 'done'), ('done_on', '>=', today)], order='done_on desc', limit=30)
        cancelled = Visit.search(mine + [('state', '=', 'cancelled'),
                                         ('cancelled_on', '>=', today - timedelta(days=CANCELLED_DAYS))],
                                 order='cancelled_on desc', limit=30)
        visits |= done | cancelled
        currency = self.env.company.currency_id
        return {
            'visits': [v._fix_tech_row() for v in visits],
            'linked': bool(me),
            'manager': manager,
            'me': me[:1].name or self.env.user.name,
            # "Done today: 3 · collected OMR 45.000"
            'today': {'done': len(done), 'collected': sum(done.mapped('paid_amount')),
                      'currency': currency.name, 'decimals': currency.decimal_places},
        }

    @api.model
    def fix_tech_search(self, query=''):
        """My Visits' search box: the technician's own visits of any date (a repair manager:
        everyone's) whose visit number (VIS/01045 or 1045), booking number (OS/01520 or 1520),
        job card, customer, phone or area matches. {count (all that match), rows (newest 50)}."""
        words = ' '.join(str(query or '').split())[:60]
        me = self._fix_tech_me()
        if len(words) < 2 or (not me and not self.env.user.has_group(MANAGER)):
            return {'count': 0, 'rows': []}
        domain = ([('technician_id', 'in', me.ids)] if me else []) + [
            '|', '|', '|', '|', '|', '|',
            ('name', 'ilike', words), ('order_id.name', 'ilike', words), ('job_card_id.name', 'ilike', words),
            ('customer_name', 'ilike', words), ('order_id.customer_name', 'ilike', words),
            ('phone', 'ilike', words), ('area', 'ilike', words)]
        Visit = self.sudo()
        return {'count': Visit.search_count(domain),
                'rows': [v._fix_tech_row() for v in Visit.search(domain, order='id desc', limit=SEARCH_LIMIT)]}

    def _fix_tech_row(self):
        self.ensure_one()
        order = self.order_id
        return {
            'id': self.id,
            'ref': self.name,
            'order': order.name or '',
            'state': self.state,
            'state_label': dict(STATES).get(self.state, self.state),
            'customer': self.customer_name or order.customer_name or '',
            'area': self.area or '',
            'summary': order.summary or '',
            'slot': {'start': _iso(self.slot_start), 'end': _iso(self.slot_end)} if self.slot_start else None,
            'created': _iso(order.create_date or self.create_date),     # when it was booked, for the list's order
            'technician': self.technician_id.name or '',
            'finishing': self.close_stage == 'finish' and self.state == 'in_progress',
            'paid': self.paid_amount or 0.0,
            'rating': self.rating or 0,
        }

    def _fix_tech_extras(self, view):
        """What only My Visits shows (the web page stays light on mobile data): the photos taken
        at this visit and a small map of the customer's place."""
        if not view or not view.get('ref'):
            return view
        visit = self.sudo()
        point = visit._fs_customer_point()
        view['photos'] = visit._co_thumbs()
        view['map_embed'] = osm_embed(*point) if point else ''
        view['map_url'] = visit.customer_map_url or ''
        # the device video from "Before you start", played in the page (its technician may read the visit)
        # (its file only: reading the field would load the whole video on every refresh)
        video = visit.env['ir.attachment'].search([('res_model', '=', visit._name), ('res_id', '=', visit.id),
                                                   ('res_field', '=', 'device_video')], limit=1)
        view['video'] = {'url': '/web/content/fix.service.visit/%d/device_video?unique=%s' % (
            visit.id, video.checksum or '')} if video else False
        return view

    def _fix_tech_mine(self):
        """This visit, as sudo with a clean context, when it is the user's own (or the user is
        a repair manager); otherwise an access error."""
        self.ensure_one()
        visit = self.sudo()
        if visit.technician_id.user_id.id != self.env.uid and not self.env.user.has_group(MANAGER):
            raise AccessError(_("This visit is not yours: only its technician (or a manager) can open it."))
        context = {key: self.env.context[key] for key in KEEP_CONTEXT if key in self.env.context}
        return visit.with_context(context, fix_tech_where=_("My Visits in Odoo"))

    def fix_tech_view(self):
        """What My Visits shows for this visit: the same as the technician's web page."""
        visit = self._fix_tech_mine()
        return visit._fix_tech_extras(visit._fs_tech_view())

    def fix_tech_act(self, action='', **kw):
        """One step from My Visits: the technician's web page's own steps, GPS pings included."""
        kw.pop('host', None)
        kw.pop('ref', None)
        kw.pop('token', None)
        visit = self._fix_tech_mine()
        result = visit._fs_tech_do(action, **kw)
        return result if action == 'ping' else visit._fix_tech_extras(result)

    def fix_tech_photo(self, photo_id=0):
        """One photo of this visit, big enough to look at closely (My Visits opens it in a popup;
        the list only carries 160 px thumbnails). Only the visit's own photos, for its technician."""
        visit = self._fix_tech_mine()
        photo = visit.env['fix.visit.check.photo'].search(
            [('id', '=', int(photo_id or 0)), ('visit_id', '=', visit.id), ('image', '!=', False)], limit=1)
        if not photo:
            return {'ok': False}
        try:
            big = image_process(base64.b64decode(photo.image), size=(1600, 1600))
        except Exception:  # noqa: BLE001 - a broken picture
            return {'ok': False}
        return {'ok': True, 'name': photo.name,
                'uri': 'data:%s;base64,%s' % (guess_mimetype(big, default='image/jpeg'), base64.b64encode(big).decode())}
