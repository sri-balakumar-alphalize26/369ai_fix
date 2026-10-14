# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DeviceCategory(models.Model):
    _inherit = 'device.category'

    web_photo_ids = fields.One2many('fix.web.image', 'category_id', string='Website photos')
    web_photo_count = fields.Integer('Photos', compute='_compute_web_photo_count', store=True)
    web_photo_id = fields.Many2one('fix.web.image', string='Photo on website', compute='_compute_web_photo', store=True)
    web_photo_preview = fields.Image('Shown photo', related='web_photo_id.image_256')

    @api.depends('web_photo_ids')
    def _compute_web_photo_count(self):
        for cat in self:
            cat.web_photo_count = len(cat.web_photo_ids)

    @api.depends('web_photo_ids', 'web_photo_ids.is_shown')
    def _compute_web_photo(self):
        for cat in self:
            photos = cat.web_photo_ids
            cat.web_photo_id = photos.filtered('is_shown')[:1] or photos[:1]

    def _fix_photo_url(self):
        self.ensure_one()
        return self.web_photo_id._web_url() if self.web_photo_id else False


class DeviceBrand(models.Model):
    _inherit = 'device.brand'

    web_logo = fields.Image('Logo', max_width=512, max_height=512)
    web_color = fields.Char('Brand colour', help="Used behind the logo on the website, e.g. #1428A0.")
    web_has_logo = fields.Boolean('Has logo', compute='_compute_web_has_logo', store=True)

    @api.depends('web_logo')
    def _compute_web_has_logo(self):
        for brand in self:
            brand.web_has_logo = bool(brand.web_logo)

    def _fix_logo_url(self):
        self.ensure_one()
        if not self.web_logo:
            return False
        stamp = int((self.write_date or fields.Datetime.now()).timestamp())
        return f'/web/image/device.brand/{self.id}/web_logo?unique={stamp}'

    def _can_return_content(self, field_name=None, access_token=None):
        if field_name == 'web_logo':
            return True
        return super()._can_return_content(field_name, access_token)
