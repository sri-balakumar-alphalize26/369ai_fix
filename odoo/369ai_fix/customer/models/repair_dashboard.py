# -*- coding: utf-8 -*-
from odoo import api, models


class MobileRepairDashboard(models.Model):
    """Adds the Online Service numbers to the repair dashboard's data."""
    _inherit = 'mobile.repair.dashboard'

    @api.model
    def get_dashboard_data(self):
        data = super().get_dashboard_data()
        try:
            Order = self.env['online.service.order']
            base = [('company_id', '=', self.env.company.id)]
            data.update({
                'online_new_doorstep': Order.search_count(base + [('state', '=', 'new'), ('mode', '=', 'doorstep')]),
                'online_new_pickup': Order.search_count(base + [('state', '=', 'new'), ('mode', '=', 'pickup')]),
                'online_new_other': Order.search_count(base + [('state', '=', 'new'), ('mode', '=', 'to_confirm')]),
                'online_open': Order.search_count(base + [('state', '=', 'confirmed')]),
            })
        except Exception:  # noqa: BLE001 - the dashboard must open even if this fails
            pass
        return data
