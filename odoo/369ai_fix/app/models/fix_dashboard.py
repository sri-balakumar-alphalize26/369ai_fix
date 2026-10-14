# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

JOB_STATES = ['draft', 'inspection', 'quotation', 'repair', 'completed', 'cancelled']
# Online Service and Website Booking numbers already added to the IT dashboard's data.
BOOKING_KEYS = ['wb_waiting', 'wb_slot_unseen', 'wb_parts', 'wb_rejected_today',
                'online_new_doorstep', 'online_new_pickup', 'online_new_other', 'online_open']


class FixDashboard(models.AbstractModel):
    """Numbers for the 369 ai Fix dashboard: website job cards, bookings and visits."""
    _name = 'fix.dashboard'
    _description = '369 ai Fix Dashboard'

    @api.model
    def get_dashboard_data(self):
        company = [('company_id', '=', self.env.company.id)]
        web_cards = company + [('online_order_id', '!=', False)]
        JobCard = self.env['job.card']
        data = {}

        # Booking counts: the same numbers the modules give the IT dashboard.
        try:
            it_data = self.env['mobile.repair.dashboard'].get_dashboard_data()
            data.update({k: it_data.get(k, 0) for k in BOOKING_KEYS})
        except Exception:  # noqa: BLE001 - the dashboard must open even if this fails
            _logger.exception("369 ai Fix dashboard: booking numbers failed")

        state_counts = {s: JobCard.search_count(web_cards + [('state', '=', s)]) for s in JOB_STATES}
        data['state_counts'] = state_counts
        data['completed'] = state_counts['completed']
        data['pending'] = sum(state_counts[s] for s in ('draft', 'inspection', 'quotation', 'repair'))

        Visit = self.env['fix.service.visit']
        today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        data['visits'] = {
            'draft': Visit.search_count(company + [('state', '=', 'draft')]),
            'assigned': Visit.search_count(company + [('state', '=', 'assigned')]),
            'on_the_way': Visit.search_count(company + [('state', '=', 'on_the_way')]),
            'at_customer': Visit.search_count(company + [('state', 'in', ('arrived', 'in_progress'))]),
            'done_today': Visit.search_count(company + [('state', '=', 'done'), ('done_on', '>=', today)]),
        }

        # Website repairs completed per month, last 12 months.
        by_month = []
        now = datetime.today()
        for i in range(11, -1, -1):
            year, month = now.year, now.month - i
            while month <= 0:
                month += 12
                year -= 1
            start = datetime(year, month, 1)
            end = datetime(year + (month == 12), month % 12 + 1, 1)
            by_month.append({
                'month': start.strftime('%m/%Y'),
                'count': JobCard.search_count(web_cards + [
                    ('state', '=', 'completed'),
                    ('completion_date', '>=', start.strftime('%Y-%m-%d')),
                    ('completion_date', '<', end.strftime('%Y-%m-%d')),
                ]),
            })
        data['completed_by_month'] = by_month
        return data
