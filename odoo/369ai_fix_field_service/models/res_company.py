# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_speed_kmh = fields.Float(
        'Average travel speed (km/h)', default=30.0,
        help="Used for the ETA: straight-line distance to the customer divided by this speed. "
             "Lower it for city traffic.")
    fs_stale_after_s = fields.Integer(
        'Position is old after (seconds)', default=120,
        help="A technician position older than this is shown as 'signal lost'.")
    fs_position_keep_days = fields.Integer(
        'Keep position trail (days)', default=7,
        help="Older trail points are deleted. The visit itself keeps its last position.")
    fs_arrival_otp = fields.Boolean(
        'Arrival code required', default=True,
        help="The technician must enter the 4-digit code the customer reads out at the door "
             "before the visit can be marked Arrived.")
    fs_show_tech_phone = fields.Boolean(
        "Show technician's phone to the customer", default=True)
