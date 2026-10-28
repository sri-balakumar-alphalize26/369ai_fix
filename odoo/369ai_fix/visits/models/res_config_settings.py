# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_speed_kmh = fields.Float(related='company_id.fs_speed_kmh', readonly=False)
    fs_stale_after_s = fields.Integer(related='company_id.fs_stale_after_s', readonly=False)
    fs_position_keep_days = fields.Integer(related='company_id.fs_position_keep_days', readonly=False)
    fs_arrival_otp = fields.Boolean(related='company_id.fs_arrival_otp', readonly=False)
    fs_show_tech_phone = fields.Boolean(related='company_id.fs_show_tech_phone', readonly=False)
    fix_warranty_days = fields.Integer(related='company_id.fix_warranty_days', readonly=False)
    fix_recheck_days = fields.Integer(related='company_id.fix_recheck_days', readonly=False)
    fix_review_url =fields.Char(related='company_id.fix_review_url', readonly=False)
    fix_no_fault_fee = fields.Boolean(related='company_id.fix_no_fault_fee', readonly=False)
    # the price of the visit fee product (Inspection and price: the inspection charge product)
    fix_visit_fee_amount = fields.Float(
        'Visit fee amount', digits='Product Price', compute='_compute_fix_visit_fee_amount',
        inverse='_inverse_fix_visit_fee_amount',
        help="The price of the visit fee product. Charged when no fault is found (switch above), "
             "and used by \"Visit fee + quote\".")

    @api.depends('company_id')
    def _compute_fix_visit_fee_amount(self):
        fee = self.env['job.card'].sudo()._visit_fee_product()
        for settings in self:
            settings.fix_visit_fee_amount = fee.lst_price if fee else 0.0

    def _inverse_fix_visit_fee_amount(self):
        fee = self.env['job.card'].sudo()._visit_fee_product()
        for settings in self:
            if fee and fee.lst_price != settings.fix_visit_fee_amount:
                fee.lst_price = max(settings.fix_visit_fee_amount, 0.0)
