# -*- coding: utf-8 -*-
"""Starter pictures, loaded on install and again from the "Load starter pictures"
button (only into empty places, so nothing chosen in Odoo is overwritten):

* each repair service's current product photo becomes the first picture of its
  gallery, shown on the website;
* the website's brand logos (static/seed/logos, made from public/brand/makers)
  go onto the brands that have no logo yet.
"""
import base64
import logging

from odoo.tools import file_open

_logger = logging.getLogger(__name__)

MODULE = '369ai_fix'

# Logo file -> brand names as they are in IT & Mobile Repair (matched without case).
LOGOS = {
    'apple': ['Apple', 'Apple macOS'],
    'samsung': ['Samsung'],
    'google': ['Google'],
    'xiaomi': ['Xiaomi'],
    'oneplus': ['OnePlus'],
    'vivo': ['Vivo'],
    'oppo': ['OPPO'],
    'realme': ['Realme'],
    'iqoo': ['iQOO'],
    'motorola': ['Motorola'],
    'nothing': ['Nothing'],
    'lenovo': ['Lenovo'],
    'dell': ['Dell'],
    'hp': ['HP'],
    'asus': ['ASUS'],
    'acer': ['Acer'],
    'msi': ['MSI'],
    'windows': ['Microsoft', 'Windows PCs'],
    'canon': ['Canon'],
    'epson': ['Epson'],
    'brother': ['Brother'],
    'hikvision': ['Hikvision'],
    'dahua': ['Dahua'],
    'tplink': ['TP-Link'],
    'ubiquiti': ['Ubiquiti'],
    'cisco': ['Cisco'],
    'dlink': ['D-Link / Netgear'],
}


def post_init_hook(env):
    load_starter_pictures(env)


def load_starter_pictures(env):
    services = _service_photos(env)
    logos = _brand_logos(env)
    _logger.info('%s: %d service photos and %d brand logos loaded', MODULE, services, logos)
    return services, logos


def _service_photos(env):
    Image = env['fix.web.image']
    templates = env['product.template'].with_context(active_test=False).search([
        ('repair_category_ids', '!=', False), ('image_1920', '!=', False), ('web_photo_ids', '=', False)])
    for tmpl in templates:
        Image.create({
            'name': tmpl.name,
            'product_tmpl_id': tmpl.id,
            'image_1920': tmpl.image_1920,
            'source': 'site',
            'is_shown': True,
        })
    return len(templates)


def _brand_logos(env):
    Brand = env['device.brand'].with_context(active_test=False)
    done = 0
    for slug, names in LOGOS.items():
        brands = Brand.browse()
        for name in names:
            brands |= Brand.search([('name', '=ilike', name), ('web_logo', '=', False)])
        if not brands:
            continue
        try:
            with file_open(f'{MODULE}/static/seed/logos/{slug}.png', 'rb') as f:
                data = base64.b64encode(f.read())
        except FileNotFoundError:
            _logger.warning('%s: logo %s missing', MODULE, slug)
            continue
        brands.write({'web_logo': data})
        done += len(brands)
    return done
