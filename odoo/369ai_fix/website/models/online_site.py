# -*- coding: utf-8 -*-
from odoo import fields, models


class OnlineServiceSite(models.Model):
    _inherit = 'online.service.site'

    show_device_photos = fields.Boolean(
        'Device photos instead of drawings',
        help="On: device types (Mobile Phones, Laptops…) show their chosen photo. "
             "Off: they show the drawing. Both stay saved, so you can switch any time.")

    def action_fix_load_starter_pictures(self):
        """Fill empty picture places from the starter set; chosen pictures are kept."""
        from ..hooks import load_starter_pictures
        services, logos = load_starter_pictures(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Starter pictures'),
                'message': self.env._('%(s)s service photos and %(l)s brand logos added.', s=services, l=logos),
                'type': 'success',
            },
        }
