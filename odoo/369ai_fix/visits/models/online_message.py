# -*- coding: utf-8 -*-
from odoo import fields, models

VISIT_KEYS = [
    ('tech_assigned', 'Visit: technician assigned'),
    ('on_the_way', 'Visit: technician on the way'),
    ('arrived', 'Visit: technician arrived'),
    ('tech_link', 'Visit: link for the technician'),
    ('visit_finish_code', 'Visit: repair done, the finish code'),
    ('visit_receipt', 'Visit: receipt, warranty and rating link'),
    ('visit_lab_check', 'Visit: device taken to the lab for a check'),
    ('visit_no_repair', 'Visit: not repaired (with the reason)'),
    ('visit_part_sourcing', 'Visit: part asked of the office, price follows'),
    ('visit_no_fault_fee', 'Visit: no fault found, the visit fee and the finish code'),
    ('visit_no_fault_receipt', 'Visit: no fault found, receipt and rating link'),
]


class OnlineServiceMessage(models.Model):
    """Three more WhatsApp texts for the doorstep visit."""
    _inherit = 'online.service.message'

    key = fields.Selection(selection_add=VISIT_KEYS,
                           ondelete={k: 'cascade' for k, _label in VISIT_KEYS})
    body = fields.Text(
        help="The message the customer gets. Tap the buttons under the box to add their name, the order number, links and more; \"Customers see\" shows how it reads.")
