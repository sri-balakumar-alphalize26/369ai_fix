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
    fix_warranty_days = fields.Integer(
        'Repair warranty (days)', default=30,
        help="The customer's receipt after a doorstep repair says the repair is under warranty until "
             "this many days later. 0: no warranty line.")
    fix_recheck_days = fields.Integer(
        'Free re-check (days)', default=7,
        help="After \"No fault found\", the customer is told: if the problem comes back within this many "
             "days, book again and the check is free (no visit fee). 0: no free re-check.")
    fix_no_fault_fee = fields.Boolean(
        'Charge a visit fee when no fault is found',
        help="On: when the technician finds nothing wrong, the customer pays the visit fee at the door, "
             "then gives the finish code (a free re-check stays free). Off: \"No fault found\" is always free.")
    fix_review_url = fields.Char(
        'Review link (Google)',
        help="Customers who give 4 or 5 stars after a visit are also offered this link "
             "(e.g. your Google review page). Empty: not offered.")
