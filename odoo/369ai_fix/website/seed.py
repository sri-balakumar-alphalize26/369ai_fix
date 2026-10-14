# -*- coding: utf-8 -*-
"""Starter content: the website's texts as they were in code on 14 Oct 2026
(data/starter_content.json, exported from the site), loaded on install, on the upgrade
that brought this in, and from the "Load starter content" button. Only empty places are
filled, so nothing staff already edited is overwritten. The website looks the same on day
one; from then on it is edited here."""
import base64
import json
import logging

from odoo.tools import file_open

_logger = logging.getLogger(__name__)

MODULE = '369ai_fix'
# device types hidden from the home tiles today (the site shows 7 of the 9)
HIDDEN_TILES = ('Printer', 'CCTV Installation')
# today's "Most booked" row, as (device category, repair service name)
MOST_BOOKED = [
    ('Mobile Phone', 'Screen replacement'), ('Mobile Phone', 'Battery replacement'),
    ('Tablet', 'Screen / glass'), ('Laptop', 'Screen replacement'), ('Laptop', 'Keyboard / trackpad'),
    ('Desktop', 'Not powering on'), ('Desktop', 'SSD / RAM upgrade'), ('Mobile Phone', 'Water damage'),
]


def load_starter_content(env, sites=None):
    with file_open(f'{MODULE}/website/data/starter_content.json') as f:
        d = json.load(f)
    sites = sites if sites is not None else env['online.service.site'].with_context(active_test=False).search([])
    pages = 0
    for site in sites:
        _fill_site(site, d)
        if not env['fix.home.page'].search_count([('site_id', '=', site.id)]):
            _make_home_page(env, site, d)
            pages += 1
    _tick_catalogue(env)
    _logger.info('%s: starter content loaded for %d website(s), %d home page(s) made', MODULE, len(sites), pages)
    return pages


def _fill_site(site, d):
    c, f = d['contact'], d['footer']
    vals = {}
    for field, value in (
        ('tagline', c.get('tagline')), ('contact_phone', c.get('phone')), ('contact_whatsapp', c.get('whatsapp')),
        ('contact_email', c.get('email')), ('contact_address', c.get('address')), ('since_year', c.get('since')),
        ('header_cta', c.get('cta')), ('footer_about', f.get('about')), ('footer_copyright', f.get('copyright')),
        ('footer_credit', f.get('credit')),
    ):
        if value and not site[field]:
            vals[field] = value
    if vals:
        site.write(vals)
    Link = site.env['fix.site.link']
    if not site.link_ids:
        Link.create([{'site_id': site.id, 'kind': 'header', 'sequence': i, 'name': n['label'], 'link': n['link']}
                     for i, n in enumerate(c.get('nav', []), 1)]
                    + [{'site_id': site.id, 'kind': 'quick', 'sequence': i, 'name': q['label'],
                        'link': _quick_link(q['label'], c)} for i, q in enumerate(f.get('quick', []), 1)])
    if not site.branch_ids:
        site.env['fix.site.branch'].create([{
            'site_id': site.id, 'sequence': i, 'name': b['name'], 'address': b.get('lines', ''),
            'phones': b.get('phones', ''), 'map_query': b.get('map', ''),
        } for i, b in enumerate(d['branches'].get('items', []), 1)])


def _quick_link(label, c):
    return {
        'Home': '/', 'Services': '/services', 'Our Team': '/team', 'My Orders': '/track',
        'Get an estimate': '/services#catalog', 'Check location': '/#check-location',
        'Book on WhatsApp': f"https://wa.me/{c.get('whatsapp', '')}",
    }.get(label, '/')


def _make_home_page(env, site, d):
    page = env['fix.home.page'].create({'name': 'Everyday page', 'site_id': site.id, 'is_current': True,
                                        'note': 'Made from the website as it was on 14 Oct 2026.'})
    Section = env['fix.home.section']
    for seq, kind in enumerate(d.get('homeOrder', []), 1):
        s = d.get(kind) or {}
        vals = {'page_id': page.id, 'kind': kind, 'sequence': seq * 10, 'active': s.get('on', True)}
        lines = []
        if kind == 'hero':
            vals.update(eyebrow=s.get('eyebrow'), title=s.get('title1'), title2=s.get('title2'), subtitle=s.get('devices'),
                        button1=s.get('btn1'), button1_link='#book-services', button2=s.get('btn2'),
                        video_url='/media/' + s['video'] if s.get('video') else False)
            lines = [{'value': x['value'], 'name': x['label']} for x in s.get('counters', [])]
        elif kind == 'services':
            vals.update(badge=s.get('badge'), title=s.get('title'), subtitle=s.get('mostTitle'), text=s.get('mostSub'),
                        button1=s.get('allLink'), button1_link='/services#all')
        elif kind == 'modes':
            vals.update(button1=s.get('foot'), button1_link='/services#coverage')
            lines = [{'name': x['title'], 'extra': x.get('short'), 'value': x.get('eta'),
                      'text': '\n'.join(p.strip() for p in (x.get('steps') or '').split('|') if p.strip())}
                     for x in s.get('cards', [])]
        elif kind == 'brands':
            vals.update(eyebrow=s.get('kicker'), title=s.get('title1'), title2=s.get('title2'))
        elif kind == 'reviews':
            vals.update(eyebrow=s.get('eyebrow'), title=s.get('title'), text=s.get('intro'))
            lines = [{'name': x['name'], 'value': x.get('area'), 'extra': x.get('service'),
                      'stars': int(x.get('stars') or 5), 'text': x.get('text')} for x in s.get('items', [])]
        elif kind == 'milestones':
            vals.update(eyebrow=s.get('eyebrow'), title=s.get('title'), text=s.get('note'))
            lines = [{'value': x['year'], 'name': x['title'], 'text': x.get('text')} for x in s.get('items', [])]
        elif kind == 'partners':
            vals.update(eyebrow=s.get('eyebrow'), title=s.get('title1'), title2=s.get('title2'), text=s.get('text'))
            for x in s.get('items', []):
                line = {'name': x['name']}
                try:
                    with file_open(f"{MODULE}/website/data/partners/{x['logo']}", 'rb') as f:
                        line['image_1920'] = base64.b64encode(f.read())
                except FileNotFoundError:
                    _logger.warning('%s: partner logo %s missing', MODULE, x.get('logo'))
                lines.append(line)
        elif kind == 'cta':
            vals.update(eyebrow=s.get('eyebrow'), title=s.get('title1'), title2=s.get('title2'), text=s.get('text'),
                        button1=s.get('button'), button1_link='/services#catalog')
            lines = [{'name': x['text']} for x in s.get('trust', [])]
        section = Section.create(vals)
        if lines:
            env['fix.home.line'].create([dict(l, section_id=section.id, sequence=i * 10) for i, l in enumerate(lines, 1)])
    return page


def _tick_catalogue(env):
    Cat = env['device.category'].with_context(active_test=False)
    hidden = Cat.search([('name', 'in', HIDDEN_TILES)])
    hidden.filtered('web_show_home').write({'web_show_home': False})
    Product = env['product.template'].with_context(active_test=False)
    if Product.search_count([('web_most_booked', '=', True)]):
        return
    seq = 0
    for cat_name, name in MOST_BOOKED:
        cat = Cat.search([('name', '=ilike', cat_name)], limit=1)
        p = Product.search([('name', '=ilike', name), ('repair_category_ids', 'in', cat.ids),
                            ('device_brand_id', '=', False), ('device_series_id', '=', False), ('device_model_id', '=', False)],
                           limit=1) if cat else Product
        if p:
            seq += 10
            p.write({'web_most_booked': True, 'web_home_sequence': seq})
