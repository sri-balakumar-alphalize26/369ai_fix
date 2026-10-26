# -*- coding: utf-8 -*-
"""Spin & Win at the visit: the technician's page (and My Visits) shows the prize on the
booking with a "Given" button; pressing it marks the win delivered. Off switch: no prize is
shown. The step is ``prize_given`` on the same door as the other steps (_fs_tech_do)."""
from odoo import _, models


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    def _spin_win(self):
        self.ensure_one()
        win = self.sudo().order_id.spin_win_id
        return win if win and win.site_id.wheel_show else win.browse()

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
        win = self._spin_win()
        if win:
            view['prize'] = {'id': win.id, 'prize': win.prize or '', 'code': win.code, 'given': bool(win.given_on),
                             'given_by': win.given_by_id.name or ''}
        return view

    def _fs_tech_do(self, action='', **args):
        if action != 'prize_given':
            return super()._fs_tech_do(action, **args)
        visit = self.sudo()
        win = visit._spin_win()
        if not win:
            return dict(visit._fs_tech_view(), ok=False, error='prize', message=_("There is no prize on this visit."))
        if visit.state != 'in_progress':
            return dict(visit._fs_tech_view(), ok=False, error='state',
                        message=_("Mark the prize given while the work is in progress."))
        win.action_mark_given(visit=visit)
        return visit._fs_tech_view()
