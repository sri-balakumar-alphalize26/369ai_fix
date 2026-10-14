# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    web_photo_ids = fields.One2many('fix.web.image', 'product_tmpl_id', string='Website photos')
    web_photo_count = fields.Integer('Photos', compute='_compute_web_photo_count', store=True)
    web_photo_id = fields.Many2one('fix.web.image', string='Photo on website', compute='_compute_web_photo', store=True)
    web_photo_preview = fields.Image('Shown photo', related='web_photo_id.image_256')

    @api.depends('web_photo_ids')
    def _compute_web_photo_count(self):
        for tmpl in self:
            tmpl.web_photo_count = len(tmpl.web_photo_ids)

    @api.depends('web_photo_ids', 'web_photo_ids.is_shown')
    def _compute_web_photo(self):
        for tmpl in self:
            photos = tmpl.web_photo_ids
            # The chosen one, else the first: a service with photos never shows blank.
            tmpl.web_photo_id = photos.filtered('is_shown')[:1] or photos[:1]

    def _fix_photo_url(self):
        self.ensure_one()
        return self.web_photo_id._web_url() if self.web_photo_id else False
