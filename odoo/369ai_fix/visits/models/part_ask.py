# -*- coding: utf-8 -*-
"""Every part the technician asked of the office at a visit, and what came of it: the office
added it (which part, at what price), said it is not available (why), or finds it later
(the purchase request), or the technician took the question back. Kept for good, one line
per question - the visit's ask_* fields only hold the question open now (visit_result.py)."""
from odoo import fields, models

ASK_RESULTS = [
    ('asked', 'Waiting for the office'),
    ('found', 'Office added the part'),
    ('none', 'Not available'),
    ('later', 'Office finds it later'),
    ('cancelled', 'Taken back'),
]


class PartAsk(models.Model):
    _name = 'fix.part.ask'
    _description = 'Part asked of the office at a visit'
    _order = 'id desc'

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade', index=True)
    job_card_id = fields.Many2one('job.card', index=True, ondelete='set null')
    order_id = fields.Many2one(related='visit_id.order_id', store=True, index=True)
    company_id = fields.Many2one(related='visit_id.company_id', store=True)
    technician_id = fields.Many2one('hr.employee', 'Technician')
    name = fields.Char('Part asked for', required=True)
    rough_price = fields.Float("Technician's rough price")
    photo = fields.Binary('Photo of the part', attachment=True)
    asked_on = fields.Datetime('Asked on', default=fields.Datetime.now)
    state = fields.Selection(ASK_RESULTS, 'Result', default='asked', required=True, index=True)
    reply = fields.Text("Office's answer")
    product_id = fields.Many2one('product.product', 'Part added')
    price = fields.Float('Price for the customer')
    answered_by_id = fields.Many2one('res.users', 'Answered by')
    answered_on = fields.Datetime('Answered on')

    def _answer(self, state, **vals):
        """Close the question with its result (only one still waiting)."""
        open_ones = self.filtered(lambda a: a.state == 'asked')
        open_ones.write(dict(vals, state=state, answered_by_id=self.env.uid, answered_on=fields.Datetime.now()))
        return open_ones

    def _row(self):
        """One line of the history, for the Booking Desk and the technician's screens."""
        self.ensure_one()
        return {
            'id': self.id,
            'visit': self.visit_id.name or '',
            'name': self.name or '',
            'rough_price': self.rough_price or 0.0,
            'asked_on': fields.Datetime.to_string(self.asked_on) if self.asked_on else '',
            'technician': self.technician_id.name or '',
            'state': self.state,
            'state_label': dict(ASK_RESULTS).get(self.state, ''),
            'reply': self.reply or '',
            'part': self.product_id.display_name or '',
            'price': self.price or 0.0,
            'by': self.answered_by_id.name or '',
            'answered_on': fields.Datetime.to_string(self.answered_on) if self.answered_on else '',
            'currency': (self.company_id or self.env.company).currency_id.name or '',
        }
