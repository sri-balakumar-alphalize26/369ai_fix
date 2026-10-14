# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

IMAGE_FIELDS = ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128')


class FixWebImage(models.Model):
    """One picture in a website gallery: a device type's photos or a repair service's photos.
    Exactly one picture per gallery is the one the website shows."""
    _name = 'fix.web.image'
    _description = 'Website picture'
    _inherit = ['image.mixin']
    _order = 'is_shown desc, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one('device.category', string='Device type', ondelete='cascade', index=True)
    product_tmpl_id = fields.Many2one('product.template', string='Repair service', ondelete='cascade', index=True)
    is_shown = fields.Boolean('Shown on website', copy=False)
    source = fields.Selection([
        ('own', 'Our own photo'),
        ('site', 'From the website'),
        ('free', 'Free photo'),
    ], default='own', required=True)
    credit = fields.Char(help="Who took the photo, for free photos that ask to be credited.")
    license = fields.Char(help="Licence of a free photo, e.g. CC0, CC BY 2.0.")
    source_url = fields.Char('Found at')

    @api.constrains('category_id', 'product_tmpl_id')
    def _check_owner(self):
        for img in self:
            if bool(img.category_id) == bool(img.product_tmpl_id):
                raise ValidationError(_("A website picture belongs to one device type or one repair service."))

    def _siblings(self):
        self.ensure_one()
        owner = ('category_id', '=', self.category_id.id) if self.category_id else ('product_tmpl_id', '=', self.product_tmpl_id.id)
        return self.search([owner, ('id', '!=', self.id)])

    def _keep_one_shown(self):
        for img in self.filtered('is_shown'):
            img._siblings().filtered('is_shown').write({'is_shown': False})

    @api.model_create_multi
    def create(self, vals_list):
        images = super().create(vals_list)
        images._keep_one_shown()
        return images

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_shown'):
            self._keep_one_shown()
        return res

    def action_show(self):
        """'Show on website' on a gallery picture."""
        self.ensure_one()
        self.is_shown = True
        return True

    def _web_url(self, size='image_512'):
        self.ensure_one()
        stamp = int((self.write_date or fields.Datetime.now()).timestamp())
        return f'/web/image/fix.web.image/{self.id}/{size}?unique={stamp}'

    def _can_return_content(self, field_name=None, access_token=None):
        # Website pictures are public: the website shows them to everyone.
        if field_name in IMAGE_FIELDS:
            return True
        return super()._can_return_content(field_name, access_token)
