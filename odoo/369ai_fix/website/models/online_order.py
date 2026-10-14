# -*- coding: utf-8 -*-
from odoo import api, models


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    @api.model
    def website_catalog(self, host):
        """The booking catalogue, plus the pictures chosen in Fix Website:
        `device_look` (drawing / photo), a photo per device type, a logo per brand
        and a photo per repair service. False where there is none, so the website
        keeps its own drawing."""
        res = super().website_catalog(host)
        if not res.get('ok'):
            return res
        site = self.env['online.service.site']._for_host(host)
        env = self.sudo().env
        photos = bool(site.show_device_photos)
        res['device_look'] = 'photo' if photos else 'drawing'
        res['drawing_style'] = site.drawing_style or '3d'
        Category, Brand, Product = env['device.category'], env['device.brand'], env['product.product']
        for cat in res.get('categories', []):
            record = Category.browse(cat['id'])
            cat['photo'] = record._fix_photo_url()
            cat['drawing'] = record._fix_drawing_url(site.drawing_style)
            cat['image'] = cat['photo'] if photos else False
            for brand in cat.get('brands', []):
                brand['logo'] = Brand.browse(brand['id'])._fix_logo_url()
            for service in cat.get('services', []):
                service['image'] = Product.browse(service['id']).product_tmpl_id._fix_photo_url()
        return res
