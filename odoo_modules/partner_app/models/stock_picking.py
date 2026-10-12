"""The last door before a delivery offer goes out.

Whoever chose the rider - the delivery module at confirm, an add-on at
Packed, clocking on, or somebody in the office - every offer goes through
`sa_action_offer`. A rider who cannot take a delivery right now (Service
only, or out on a service visit) is swapped here for one who can, or the job
goes back to To Dispatch.
"""

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def sa_action_offer(self):
        Rider = self.env['sa.delivery.partner']
        for picking in self:
            rider = picking.sa_delivery_partner_id
            if not rider or rider._partner_app_can_deliver():
                continue
            why = (_("is on service visit %s", rider.service_job_ref)
                   if rider.service_job_ref else _("works in Service only"))
            new = Rider._partner_app_pick_for_delivery(picking.sa_shop_id)
            picking.sa_delivery_partner_id = new
            picking.message_post(body=_(
                "%(rider)s %(why)s - offered to %(new)s instead.",
                rider=rider.name, why=why,
                new=new.name if new else _("nobody (back to To Dispatch)")))
            _logger.info("Partner app: job %s not offered to %s (%s), now %s",
                         picking.sa_ref_code, rider.name, why,
                         new.name if new else 'nobody')
        return super().sa_action_offer()
