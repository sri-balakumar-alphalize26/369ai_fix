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
    # Added 14 Oct 2026: Simple Icons (CC0) and the brands' own Wikimedia Commons logo files
    'huawei': ['Huawei'],
    'honor': ['Honor'],
    'sony': ['Sony'],
    'lg': ['LG'],
    'nokia': ['Nokia'],
    'garmin': ['Garmin'],
    'panasonic': ['Panasonic'],
    'razer': ['Razer'],
    'toshiba': ['Dynabook (Toshiba)'],
    'framework': ['Framework'],
    'amazfit': ['Amazfit'],
    'gigabyte': ['Gigabyte'],
    'ricoh': ['Ricoh'],
    'xerox': ['Xerox'],
    'infinix': ['Infinix'],
    'tecno': ['Tecno'],
    'itel': ['Itel'],
    'lava': ['Lava'],
    'micromax': ['Micromax'],
    'cpplus': ['CP Plus'],  # text logo until the real one is uploaded in Brand Logos
    # Not brands: simple icons
    'flashcards': ['Flash & cards'],
    'harddisks': ['Hard disks'],
    'ssds': ['SSDs'],
    'officeemail': ['Office & email'],
    'wificameras': ['Home Wi-Fi cameras'],
}


def post_init_hook(env):
    load_starter_pictures(env)


# Device type -> drawing in static/seed/drawings (the website's own illustrations, plus a watch).
DRAWINGS = {
    'Mobile Phone': 'phone',
    'Tablet': 'tablet',
    'Laptop': 'laptop',
    'Desktop': 'desktop',
    'Printer': 'printer',
    'CCTV Installation': 'cctv',
    'Networking & Wi-Fi': 'router',
    'Data Recovery': 'drive',
    'IT Support': 'support',
    'Smartwatch': 'watch',
}


def load_starter_pictures(env):
    services = _service_photos(env)
    logos = _brand_logos(env)
    _device_drawings(env)
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


# Drawing style -> (field, folder under static/seed/drawings); 3D sits in the folder itself.
DRAWING_STYLE_FILES = {
    'web_drawing': '',
    'web_drawing_line': 'line/',
    'web_drawing_flat': 'flat/',
    'web_drawing_sketch': 'sketch/',
    'web_drawing_duotone': 'duotone/',
}


def _device_drawings(env):
    Category = env['device.category'].with_context(active_test=False)
    done = 0
    for name, slug in DRAWINGS.items():
        for field, folder in DRAWING_STYLE_FILES.items():
            cats = Category.search([('name', '=ilike', name), (field, '=', False)])
            if not cats:
                continue
            try:
                with file_open(f'{MODULE}/static/seed/drawings/{folder}{slug}.png', 'rb') as f:
                    cats.write({field: base64.b64encode(f.read())})
                    done += len(cats)
            except FileNotFoundError:
                _logger.warning('%s: drawing %s%s missing', MODULE, folder, slug)
    return done


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
