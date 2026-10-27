# -*- coding: utf-8 -*-
"""The office's answer to a part the technician asked for at the door (visit_result.py):
the part from the list, or a new one by its name, at a price - added to the job card, and
the technician's screen shows it. "Not available" is a button on the Booking Desk."""
from odoo import api, fields, models


class PartAskWizard(models.TransientModel):
    _name = 'fix.part.ask.wizard'
    _description = "Answer the technician's part question"

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade')
    asked = fields.Char('The technician asks for', compute='_compute_asked')
    # the device type: only parts that fit it are offered (the green pop-up's pick_domain)
    category_id = fields.Many2one('device.category', compute='_compute_asked')
    product_id = fields.Many2one('product.product', 'Part', domain=[('type', '=', 'consu'), ('sale_ok', '=', True)],
                                 help="The part from the list. Not in the list: type its name below instead.")
    new_name = fields.Char('Or a new part', help="Not in the list: the part is made with this name and price.")
    price = fields.Float('Price for the customer', help="Empty: the part's own price.")
    note = fields.Char('Note for the technician', help="e.g. \"In the office drawer\" or \"Arrives tomorrow\".")

    @api.depends('visit_id')
    def _compute_asked(self):
        for wiz in self:
            visit = wiz.visit_id.sudo()
            wiz.asked = '%s (about %s)' % (visit.ask_name, visit.ask_price) if visit.ask_name else ''
            wiz.category_id = visit._vr_device()[0] if visit else False

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id and not self.price:
            self.price = self.product_id.lst_price

    def action_confirm(self):
        self.ensure_one()
        self.visit_id._vr_ask_found(product=self.product_id, price=self.price or None, new_name=self.new_name,
                                    note=self.note)
        return {'type': 'ir.actions.act_window_close'}
