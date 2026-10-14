# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Drawing style -> field on device.category
DRAWING_STYLES = [('3d', '3D'), ('line', 'Line'), ('flat', 'Flat'), ('sketch', 'Sketch'), ('duotone', 'Duotone')]
DRAWING_FIELDS = {'3d': 'web_drawing', 'line': 'web_drawing_line', 'flat': 'web_drawing_flat',
                  'sketch': 'web_drawing_sketch', 'duotone': 'web_drawing_duotone'}


class DeviceCategory(models.Model):
    _inherit = 'device.category'

    web_photo_ids = fields.One2many('fix.web.image', 'category_id', string='Website photos')
    web_photo_count = fields.Integer('Photos', compute='_compute_web_photo_count', store=True)
    web_photo_id = fields.Many2one('fix.web.image', string='Photo on website', compute='_compute_web_photo', store=True)
    web_photo_preview = fields.Image('Shown photo', related='web_photo_id.image_256')
    # The drawing (illustration) the website shows when the site toggle is on "drawings".
    # The drawing in 5 styles; the website uses the style chosen in Device Pictures.
    web_drawing = fields.Image('3D', max_width=512, max_height=512,
                               help="Drawing in the 3D style (the website's original illustration).")
    web_drawing_line = fields.Image('Line', max_width=512, max_height=512)
    web_drawing_flat = fields.Image('Flat', max_width=512, max_height=512)
    web_drawing_sketch = fields.Image('Sketch', max_width=512, max_height=512)
    web_drawing_duotone = fields.Image('Duotone', max_width=512, max_height=512)
    web_has_drawing = fields.Boolean('Has drawing', compute='_compute_web_has_drawing', store=True)

    @api.depends('web_photo_ids')
    def _compute_web_photo_count(self):
        for cat in self:
            cat.web_photo_count = len(cat.web_photo_ids)

    @api.depends('web_drawing')
    def _compute_web_has_drawing(self):
        for cat in self:
            cat.web_has_drawing = bool(cat.web_drawing)

    # What the website shows for this device type right now: its drawing or its chosen photo,
    # following the site switch (Device Pictures header buttons / Website Details toggle).
    web_look = fields.Selection([('drawing', 'Drawing sketch'), ('photo', 'Real photo')],
                                string='Website shows', compute='_compute_web_shown')

    @api.model
    def _fix_sites(self):
        return self.env['online.service.site'].sudo().search([('active', '=', True)])

    @api.depends('web_drawing', 'web_photo_id')
    @api.depends_context('uid')
    def _compute_web_shown(self):
        photos = any(self._fix_sites().mapped('show_device_photos'))
        for cat in self:
            cat.web_look = 'photo' if photos else 'drawing'

    def action_fix_open_pictures(self):
        """"Edit pictures" on a device type in the Device Pictures screen."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'device.category',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('369ai_fix.view_device_category_pictures_form').id, 'form')],
            'target': 'current',
        }

    def _fix_drawing_url(self, style='3d'):
        """The drawing in this style, else the 3D one."""
        self.ensure_one()
        field = DRAWING_FIELDS.get(style, 'web_drawing')
        if not self[field]:
            field = 'web_drawing'
        if not self[field]:
            return False
        stamp = int((self.write_date or fields.Datetime.now()).timestamp())
        return f'/web/image/device.category/{self.id}/{field}?unique={stamp}'

    def _can_return_content(self, field_name=None, access_token=None):
        if field_name in DRAWING_FIELDS.values():
            return True
        return super()._can_return_content(field_name, access_token)

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
