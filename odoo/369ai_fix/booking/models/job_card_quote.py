# -*- coding: utf-8 -*-
"""The formal quotation at the visit, measured against the estimate the customer
accepted before it; taking a device to the office; and the price check when an
ordered part turns out dearer than expected."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

QUOTE_STATES = [
    ('none', 'No estimate'),
    ('accepted', 'Customer accepted'),
    ('waiting', 'Waiting for the customer'),
    ('declined', 'Customer declined'),
]


class JobCard(models.Model):
    _inherit = 'job.card'

    estimate_total = fields.Float('Estimate accepted', readonly=True, copy=False,
                                  help="What the customer agreed to before the visit (repairs + parts).")
    estimate_accepted_on = fields.Datetime(readonly=True, copy=False)
    quote_state = fields.Selection(QUOTE_STATES, default='none', readonly=True, copy=False, tracking=True)
    wb_at_office = fields.Boolean('Device at our office', readonly=True, copy=False, tracking=True)
    wb_taken_on = fields.Datetime('Taken to office on', readonly=True, copy=False)
    wb_taken_by_id = fields.Many2one('res.users', 'Taken by', readonly=True, copy=False)
    wb_return_by = fields.Date('Return by', readonly=True, copy=False)
    wb_returned = fields.Boolean('Returned to customer', readonly=True, copy=False)

    def _wb_lines_total(self):
        """Repairs + parts; of two grades offered for one part, only the one chosen counts."""
        self.ensure_one()
        return sum(l.unit_price * l.quantity for l in self.service_line_ids) + \
            sum(l.unit_price * l.quantity for l in self.spare_part_line_ids.filtered(lambda l: not l.fix_alt_off))

    def _wb_alt_groups(self):
        """{key: lines} of the parts offered in two grades (original / compatible)."""
        self.ensure_one()
        groups = {}
        for line in self.spare_part_line_ids.filtered('fix_alt_key'):
            groups.setdefault(line.fix_alt_key, self.env['job.card.spare.part.line'])
            groups[line.fix_alt_key] |= line
        return groups

    def _wb_choose_alts(self, chosen_ids=()):
        """Keep one grade of each part offered in two: the line in `chosen_ids`, else the one
        chosen so far. The other grades are removed, so ordering and the bill see one part."""
        chosen_ids = {int(x) for x in (chosen_ids or []) if str(x).isdigit()}
        for card in self:
            for key, lines in card._wb_alt_groups().items():
                keep = lines.filtered(lambda l: l.id in chosen_ids)[:1] or lines.filtered(lambda l: not l.fix_alt_off)[:1] \
                    or lines[:1]
                gone = lines - keep
                if gone:
                    card.message_post(body=_("Customer's choice: %(kept)s (not %(gone)s).",
                                             kept=keep.description or keep.product_id.name,
                                             gone=', '.join(gone.mapped(lambda l: l.description or l.product_id.name))))
                    gone.unlink()
                keep.write({'fix_alt_key': False, 'fix_alt_off': False})

    # ------------------------------------------------------------------
    # Quotation at the visit
    # ------------------------------------------------------------------
    def action_create_quotation(self):
        res = super().action_create_quotation()
        for card in self.filtered(lambda c: c.online_order_id and c.estimate_accepted_on):
            currency = card.company_id.currency_id
            total = card._wb_lines_total()
            if currency.compare_amounts(total, card.estimate_total) == 0:
                card.quote_state = 'accepted'
                card.message_post(body=_("The quotation matches the estimate the customer accepted: the repair can start."))
            else:
                card._wb_send_new_price()
        return res

    def _wb_send_new_price(self, timeline=''):
        """The price changed: ask the customer again (Approve / Decline on the website).
        `timeline`: what happens once they approve (the technician's plan, visits/)."""
        for card in self:
            order = card.online_order_id
            card.quote_state = 'waiting'
            estimate, total = order._wb_estimate()
            link = order._wb_new_slot_link().replace('/slot?', '/quote?')
            missing = card.spare_part_line_ids.filtered(
                lambda l: not l.fix_alt_off and l.product_id.qty_available < (l.quantity or 1))
            order._wb_notify('quote_changed', estimate=estimate, quote_url=link,
                             old_total='%.3f' % card.estimate_total, new_total='%.3f' % total,
                             parts=', '.join(missing.mapped(lambda l: l.description or l.product_id.name)),
                             timeline=timeline)
            card.message_post(body=_("New price %(new).3f (estimate was %(old).3f): sent to the customer to approve.",
                                     new=total, old=card.estimate_total))

    def action_wb_send_new_price(self):
        """Staff send the updated price again (e.g. after a part came dearer)."""
        for card in self:
            if not card.online_order_id:
                raise UserError(_("Only for job cards from a website booking."))
        self._wb_send_new_price()
        return True

    def action_start_repair(self):
        for card in self:
            if card.quote_state == 'waiting':
                raise UserError(_("Waiting for the customer to approve the new price. "
                                  "If they approved by phone, press \"Customer approved by phone\"."))
        return super().action_start_repair()

    def action_wb_approved_by_phone(self):
        for card in self.filtered(lambda c: c.quote_state in ('waiting', 'declined')):
            card._wb_quote_approved(by=_("%s, by phone", self.env.user.name))
        return True

    def _wb_quote_approved(self, by=None):
        self.ensure_one()
        self._wb_choose_alts()          # an approval without a choice keeps the grade shown first
        self.write({'quote_state': 'accepted', 'estimate_total': self._wb_lines_total()})
        self.message_post(body=_("Customer approved the new price%s.", (_(" (noted by %s)", by) if by else '')))
        order = self.online_order_id
        missing = self.spare_part_line_ids.filtered(lambda l: l.product_id.qty_available < (l.quantity or 1))
        if missing and order and order.parts_state != 'ordering':
            order.sudo().write({'parts_state': 'ask'})
            order._wb_order_parts()         # the visit waits: a new time is booked when they arrive
        elif order and order.parts_state == 'ordering' and order.wb_requote_needed:
            # The re-priced part is already here: the price is agreed, open the slots.
            open_requests = self.env['spare.part.purchase.request'].sudo().search_count(
                [('job_card_id', 'in', order.job_card_ids.ids), ('state', 'not in', ('received', 'rejected'))])
            if not open_requests:
                order.sudo().write({'parts_state': 'ready', 'wb_requote_needed': False})
                order._wb_notify('part_arrived', slot_url=order._wb_new_slot_link())
        # the technician's plan sent with the quotation goes ahead (visits/visit_result.py)
        self.sudo().fs_visit_ids.filtered('pend_plan')._vr_approved()

    # ------------------------------------------------------------------
    # Take the device to the office (accessories must be recorded)
    # ------------------------------------------------------------------
    def action_wb_take_to_office(self):
        self.ensure_one()
        if self.state not in ('inspection', 'quotation'):
            raise UserError(_("Take the device to the office during inspection or quotation."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Take %s to the office", self.name),
            'res_model': 'wb.office.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_job_card_id': self.id,
                        'default_accessory_ids': [(6, 0, self.accessory_ids.ids)],
                        'default_accessories': self.accessories},
        }

    def write(self, vals):
        before = {c.id: c.state for c in self} if 'state' in vals else {}
        res = super().write(vals)
        if before:
            for card in self.filtered(lambda c: c.wb_at_office and not c.wb_returned and c.online_order_id):
                if card.state == 'completed' and before.get(card.id) != 'completed':
                    card._wb_plan_return(_("Your device is repaired and ready."))
        return res

    def _wb_plan_return(self, why):
        """A visit to bring the device back; the customer picks the time."""
        self.ensure_one()
        order = self.online_order_id.sudo()
        order.write({'slot_id': False, 'slot_date': False, 'slot_booked_on': False, 'parts_state': 'ready'})
        vals = order._fs_visit_vals()
        vals['job_card_id'] = self.id
        order.env['fix.service.visit'].create(vals)
        order._wb_notify('return_ready', reason=why, slot_url=order._wb_new_slot_link())
        self.message_post(body=_("Return visit created; the customer was sent the link to pick a time."))

    @api.model
    def _wb_decline_at_office(self):
        """Customer declined the office quotation: bring the device back unrepaired."""
        for card in self.filtered(lambda c: c.wb_at_office and not c.wb_returned):
            card._wb_plan_return(_("We will bring your device back."))


class JobCardSparePartLine(models.Model):
    """Two grades of the same part (original / compatible) offered side by side: the customer
    keeps one on the quotation link, or tells the technician at the door."""
    _inherit = 'job.card.spare.part.line'

    fix_alt_key = fields.Char('Offered with', copy=False,
                              help="Lines with the same key are grades of one part: the customer keeps one.")
    fix_alt_off = fields.Boolean('Not chosen (yet)', copy=False,
                                 help="The other grade is the one chosen so far: this line is not in the total.")
