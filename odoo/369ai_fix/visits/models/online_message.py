# -*- coding: utf-8 -*-
from odoo import fields, models

VISIT_KEYS = [
    ('tech_assigned', 'Visit: technician assigned'),
    ('on_the_way', 'Visit: technician on the way'),
    ('arrived', 'Visit: technician arrived'),
    ('tech_link', 'Visit: link for the technician'),
]


class OnlineServiceMessage(models.Model):
    """Three more WhatsApp texts for the doorstep visit."""
    _inherit = 'online.service.message'

    key = fields.Selection(selection_add=VISIT_KEYS,
                           ondelete={k: 'cascade' for k, _label in VISIT_KEYS})
    body = fields.Text(
        help="Placeholders: {name} customer, {order} order no., {status}, {job_card} job card no., "
             "{site} website name, {track_url} tracking link, {summary} what was booked. "
             "Visit messages also have {technician}, {technician_phone}, {eta} (e.g. 'about 15 min') "
             "and {code} (the arrival code). The technician's link message has {tech_url} "
             "(their visit page, which shares their location), {area} and {address}.")
