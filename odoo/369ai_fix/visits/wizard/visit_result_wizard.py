# -*- coding: utf-8 -*-
"""The "What did you find?" window (visit form, Booking Desk): visits/models/visit_result.py
does the work; this only collects the answer - the parts, and the plan sent with the
quotation."""
from odoo import _, api, fields, models

from ..models.visit_result import PLANS

STATUS = [('in_stock', 'In the office'), ('other_branch', 'At another branch'), ('order', 'Must be ordered')]


class VisitResultWizard(models.TransientModel):
    _name = 'fix.visit.result.wizard'
    _description = 'What did you find?'

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade')
    need_device = fields.Boolean(compute='_compute_need_device')
    category_id = fields.Many2one('device.category', 'Device')
    brand_id = fields.Many2one('device.brand', 'Brand')
    model_id = fields.Many2one('device.model', 'Model', domain="[('brand_id', '=', brand_id)]")
    found = fields.Text('What did you find?')
    line_ids = fields.One2many('fix.visit.result.wizard.line', 'wizard_id', 'Parts needed')
    to_order = fields.Boolean(compute='_compute_need')
    has_parts = fields.Boolean(compute='_compute_need')
    plan_here = fields.Selection([p for p in PLANS if p[0] in ('now', 'take', 'come_back')],
                                 'After the customer approves', default='now')
    plan_order = fields.Selection([p for p in PLANS if p[0] in ('keep', 'order_take')],
                                  'While the part comes', default='keep')
    days = fields.Integer('Fixed within', default=3,
                          help="Part in the office: the repair time. Part to order and the device goes to the "
                               "office: the repair time after the part arrives.")
    days_unit = fields.Selection([('days', 'days'), ('weeks', 'weeks')], default='days', required=True)
    part_days = fields.Integer('Part arrives in about (days)',
                               default=lambda self: self._default_part_days())

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        visit = self.env['fix.service.visit'].browse(res.get('visit_id') or self.env.context.get('default_visit_id'))
        if visit:
            res['found'] = visit.check_found
            cat, brand, _series, model = visit._vr_device_guess()
            card = visit.sudo().job_card_id
            res['category_id'] = (card.device_category_id or cat).id
            res['brand_id'] = (card.brand_id or brand).id
            res['model_id'] = (card.model_id or model).id
            res['line_ids'] = [(0, 0, {'product_id': l.product_id.id, 'qty': l.quantity})
                               for l in card.spare_part_line_ids] if card else []
        return res

    @api.model
    def _default_part_days(self):
        visit = self.env['fix.service.visit'].browse(self.env.context.get('default_visit_id'))
        return visit.sudo().order_id.parts_days or 7

    @api.depends('visit_id')
    def _compute_need_device(self):
        for wiz in self:
            wiz.need_device = not wiz.visit_id.sudo().job_card_id

    @api.depends('line_ids.status', 'line_ids.product_id')
    def _compute_need(self):
        for wiz in self:
            lines = wiz.line_ids.filtered('product_id')
            wiz.has_parts = bool(lines)
            wiz.to_order = 'order' in lines.mapped('status')

    def _sync(self):
        """The answer onto the visit and its job card's spare lines."""
        self.ensure_one()
        visit = self.visit_id
        visit._vr_note(self.found)
        lines = self.line_ids.filtered('product_id')
        if not lines and not visit.sudo().job_card_id:
            return
        card = visit._vr_card(brand=self.brand_id, model=self.model_id, category=self.category_id)
        for line in lines:
            visit._vr_add_part(line.product_id, line.qty or 1.0)
        card.sudo().spare_part_line_ids.filtered(lambda l: l.product_id not in lines.product_id).unlink()
        visit._vr_note(self.found)

    def action_fixed(self):
        self.ensure_one()
        self._sync()
        self.visit_id._vr_fixed(self.found)
        return {'type': 'ir.actions.act_window_close'}

    def action_quote(self):
        """Quote first: the parts, the price and the plan go to the customer to approve."""
        self.ensure_one()
        self._sync()
        plan = self.plan_order if self.to_order else self.plan_here
        self.visit_id._vr_send_quote(plan, days=self.days, unit=self.days_unit, part_days=self.part_days)
        return {'type': 'ir.actions.act_window_close'}


class VisitResultWizardLine(models.TransientModel):
    _name = 'fix.visit.result.wizard.line'
    _description = 'What did you find? - part'

    wizard_id = fields.Many2one('fix.visit.result.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Part', domain=[('type', '=', 'consu')])
    qty = fields.Float('Qty', default=1.0)
    status = fields.Selection(STATUS, compute='_compute_stock')
    where = fields.Char('Where', compute='_compute_stock')
    price = fields.Float(related='product_id.lst_price')

    @api.depends('product_id', 'qty', 'wizard_id.visit_id')
    def _compute_stock(self):
        for line in self:
            if not line.product_id or not line.wizard_id.visit_id:
                line.status = False
                line.where = ''
                continue
            stock = line.wizard_id.visit_id._vr_stock(line.product_id, line.qty or 1.0)
            line.status = stock['status']
            if stock['status'] == 'in_stock':
                line.where = _("In the office: %s", '%g' % stock['office'])
            elif stock['status'] == 'other_branch':
                line.where = _("At %s", ', '.join('%s (%g)' % (b['name'], b['qty']) for b in stock['branches']))
            else:
                line.where = _("Not in stock - must be ordered")
