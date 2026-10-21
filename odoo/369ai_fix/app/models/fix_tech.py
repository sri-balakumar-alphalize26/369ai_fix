# -*- coding: utf-8 -*-
"""My Visits: the technician's own screen in Odoo (static/src/app/tech/).

The same steps as the technician's web page from WhatsApp (visits/: `_fs_tech_do`), reached
with the technician's own Odoo login instead of the link. A technician sees and changes only
the visits they are the technician of (their employee is linked to their user); a repair
manager can open any visit, to help or to test. Office staff keep the Booking Desk.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ...visits.models.service_visit import OPEN_STATES, STATES, _iso

MANAGER = 'mobile_repair.group_mobile_repair_manager'
# only these keys of the caller's context reach the steps: a client cannot pass flags such
# as fix_checks_passed or wb_silent through My Visits
KEEP_CONTEXT = ('lang', 'tz', 'allowed_company_ids')


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    @api.model
    def _fix_tech_me(self):
        return self.env['hr.employee'].sudo().search([('user_id', '=', self.env.uid)])

    @api.model
    def fix_tech_load(self):
        """My visits: the open ones (the soonest first), then the ones finished today.
        A repair manager without an employee of their own sees every technician's."""
        me = self._fix_tech_me()
        manager = self.env.user.has_group(MANAGER)
        if not me and not manager:
            return {'visits': [], 'linked': False, 'manager': False, 'me': self.env.user.name}
        mine = [('technician_id', 'in', me.ids)] if me else []
        Visit = self.sudo()
        today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        visits = Visit.search(mine + [('state', 'in', OPEN_STATES)], order='slot_start asc, id asc', limit=100)
        visits |= Visit.search(mine + [('state', '=', 'done'), ('done_on', '>=', today)],
                               order='done_on desc', limit=30)
        return {
            'visits': [v._fix_tech_row() for v in visits],
            'linked': bool(me),
            'manager': manager,
            'me': me[:1].name or self.env.user.name,
        }

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
            'technician': self.technician_id.name or '',
        }

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
        return self._fix_tech_mine()._fs_tech_view()

    def fix_tech_act(self, action='', **kw):
        """One step from My Visits: the technician's web page's own steps, GPS pings included."""
        kw.pop('host', None)
        kw.pop('ref', None)
        kw.pop('token', None)
        return self._fix_tech_mine()._fs_tech_do(action, **kw)
