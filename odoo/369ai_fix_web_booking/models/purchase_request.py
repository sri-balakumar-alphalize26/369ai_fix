# -*- coding: utf-8 -*-
"""Parts ordered for a website booking: the customer hears when they are ordered,
when they are late, and when they have all arrived (with the link to pick a time)."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class SparePartPurchaseRequest(models.Model):
    _inherit = 'spare.part.purchase.request'

    expected_date = fields.Date('Expected arrival', tracking=True,
                                help="Required when ordering: the customer is told this date.")

    def _wb_orders(self):
        return self.mapped('job_card_id.online_order_id').filtered(lambda o: o.state != 'cancelled')

    def write(self, vals):
        before = {r.id: (r.state, r.expected_date) for r in self}
        res = super().write(vals)
        for req in self:
            old_state, old_date = before.get(req.id, (None, None))
            if req.state == 'ordered' and not req.expected_date:
                raise UserError(_("Enter the expected arrival date first: the customer is told when the part comes."))
            orders = req._wb_orders()
            if not orders:
                continue
            if req.state == 'ordered' and old_state != 'ordered':
                for order in orders:
                    order._wb_notify('part_ordered', part=req.product_name,
                                     date=req.expected_date.strftime('%d %b'))
            elif req.state == 'ordered' and old_date and req.expected_date and req.expected_date > old_date:
                for order in orders:
                    order._wb_notify('part_delayed', part=req.product_name,
                                     date=req.expected_date.strftime('%d %b'))
            if req.state == 'received' and old_state != 'received':
                for order in orders:
                    req._wb_maybe_ready(order)
        return res

    def _wb_real_cost(self):
        """Unit cost on the purchase order, or 0 when not known."""
        self.ensure_one()
        po = self.purchase_order_id
        line = po.order_line[:1] if po else None
        return line.price_unit if line else 0.0

    def _wb_maybe_ready(self, order):
        """All parts for this booking are in: open the slots and send the link - unless a
        part came more than the allowed % dearer, then staff re-price it first."""
        all_requests = self.search([('job_card_id', 'in', order.job_card_ids.ids)])
        if all_requests.filtered(lambda r: r.state not in ('received', 'rejected')) \
                or order.parts_state != 'ordering':
            return
        limit = (order.company_id or self.env.company).repair_requote_pct or 0.0
        dearer = all_requests.filtered(lambda r: r.estimated_cost and r._wb_real_cost()
                                       and r._wb_real_cost() > r.estimated_cost * (1 + limit / 100.0))
        if dearer:
            order.sudo().write({'wb_requote_needed': True})
            names = ', '.join('%s (%.3f instead of %.3f)' % (r.product_name, r._wb_real_cost(), r.estimated_cost)
                              for r in dearer)
            order.message_post(body=_("Parts arrived, but cost more than %(pct)s%% over the estimate: %(names)s. "
                                      "Update the price on the job card and press \"Send new price\".",
                                      pct=limit, names=names))
            for card in order.job_card_ids:
                card.activity_schedule('mail.mail_activity_data_todo', summary=_("Part dearer than expected: re-price"),
                                       note=names, user_id=(order.approved_by_id or self.env.user).id)
            return
        order.sudo().write({'parts_state': 'ready'})
        order._wb_notify('part_arrived', slot_url=order._wb_new_slot_link())
        order.message_post(body=_("All ordered parts have arrived: the customer was sent the link to pick a time."))
