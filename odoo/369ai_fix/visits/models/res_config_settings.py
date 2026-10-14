# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_speed_kmh = fields.Float(related='company_id.fs_speed_kmh', readonly=False)
    fs_stale_after_s = fields.Integer(related='company_id.fs_stale_after_s', readonly=False)
    fs_position_keep_days = fields.Integer(related='company_id.fs_position_keep_days', readonly=False)
    fs_arrival_otp = fields.Boolean(related='company_id.fs_arrival_otp', readonly=False)
    fs_show_tech_phone = fields.Boolean(related='company_id.fs_show_tech_phone', readonly=False)
