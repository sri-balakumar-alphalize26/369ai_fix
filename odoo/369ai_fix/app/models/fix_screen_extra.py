# -*- coding: utf-8 -*-
"""What a green screen shows besides fields: the visit's live map (the Booking Desk's)."""
from odoo import models


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    def _fix_screen_extra(self, key):
        self.ensure_one()
        return {'map': self.env['online.service.order']._fix_desk_map(self.sudo())}
