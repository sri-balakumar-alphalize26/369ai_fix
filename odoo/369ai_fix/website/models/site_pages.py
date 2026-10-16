# -*- coding: utf-8 -*-
"""Round 2 of editing the website from Odoo: the areas the site covers (doorstep and pickup
zones), the FAQs and the info pages (About, Privacy, Terms…). Each belongs to one Website
record and goes to the site inside ``website_content`` (see site_content.py)."""
import logging
import re

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_NOMINATIM = 'https://nominatim.openstreetmap.org/search'
MODES = [('doorstep', 'Doorstep'), ('pickup', 'Pickup')]


class FixCoverageZone(models.Model):
    _name = 'fix.coverage.zone'
    _description = 'Website coverage zone'
    _order = 'mode, sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade', string='Website',
                              default=lambda self: self.env['online.service.site'].search([], limit=1))
    mode = fields.Selection(MODES, string='Service', required=True, default='doorstep')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Zone', required=True,
                       help='As it reads on the site. A branch in brackets shows under the zone name, '
                            'e.g. "Muscat (Ruwi branch)".')
    latitude = fields.Float(string='Map centre (latitude)', digits=(9, 6))
    longitude = fields.Float(string='Map centre (longitude)', digits=(9, 6))
    area_ids = fields.One2many('fix.coverage.area', 'zone_id', string='Areas')
    area_count = fields.Integer(compute='_compute_area_count', string='Number of areas')

    @api.depends('area_ids')
    def _compute_area_count(self):
        for zone in self:
            zone.area_count = len(zone.area_ids)

    def _pin(self):
        """The zone's map centre: its own, else the first area that has one."""
        self.ensure_one()
        if self.latitude or self.longitude:
            return [self.latitude, self.longitude]
        area = self.area_ids.filtered(lambda a: a.latitude or a.longitude)[:1]
        return [area.latitude, area.longitude] if area else False

    def _serialize(self):
        self.ensure_one()
        return {'name': self.name, 'areas': self.area_ids.sorted('sequence').mapped('name'), 'pin': self._pin()}


class FixCoverageArea(models.Model):
    _name = 'fix.coverage.area'
    _description = 'Website coverage area'
    _order = 'sequence, id'

    zone_id = fields.Many2one('fix.coverage.zone', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Area', required=True)
    latitude = fields.Float(digits=(9, 6),
                            help='Found on OpenStreetMap when the area is saved. The "check my location" box '
                                 'on the site uses it to recognise the area.')
    longitude = fields.Float(digits=(9, 6))

    @api.model_create_multi
    def create(self, vals_list):
        areas = super().create(vals_list)
        areas._fix_find_position()
        return areas

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals and 'latitude' not in vals and 'longitude' not in vals:
            self._fix_find_position(force=True)
        return res

    def _fix_find_position(self, force=False):
        """Look the area up on OpenStreetMap (Oman only). Never stops the save: no answer
        just leaves the position empty for staff to type in."""
        if self.env.context.get('fix_no_geocode'):
            return
        for area in self:
            if not force and (area.latitude or area.longitude):
                continue
            try:
                reply = requests.get(_NOMINATIM, timeout=5, params={
                    'q': area.name, 'countrycodes': 'om', 'format': 'json', 'limit': 1,
                }, headers={'User-Agent': 'danatfix-website/1.0'})
                hits = reply.json() if reply.ok else []
            except Exception as e:  # network down, slow, blocked
                _logger.info('369ai_fix: no map position for area %r (%s)', area.name, e)
                continue
            if hits:
                super(FixCoverageArea, area).write({'latitude': float(hits[0]['lat']), 'longitude': float(hits[0]['lon'])})


class FixSiteFaq(models.Model):
    _name = 'fix.site.faq'
    _description = 'Website FAQ'
    _order = 'sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade', string='Website',
                              default=lambda self: self.env['online.service.site'].search([], limit=1))
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Question', required=True)
    answer = fields.Text(required=True, help='{price} becomes the visit fee, e.g. OMR 5, or "price after check" when none is set.')


class FixSitePage(models.Model):
    _name = 'fix.site.page'
    _description = 'Website info page'
    _order = 'sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade', string='Website',
                              default=lambda self: self.env['online.service.site'].search([], limit=1))
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Title', required=True)
    slug = fields.Char(string='Web address', required=True,
                       help='The page opens at /page/<web address>, e.g. "about" → /page/about.')
    column = fields.Selection([('company', 'Company'), ('help', 'Help'), ('policies', 'Policies'), ('none', 'Not in the footer')],
                              string='Footer column', required=True, default='company')
    kind = fields.Selection([('text', 'Text page'), ('contact', 'Contact (fills itself)'),
                             ('areas', 'Areas we cover (fills itself)'), ('faq', 'FAQ (fills itself)')],
                            required=True, default='text',
                            help='Contact shows the contact details and branches, Areas the coverage areas, '
                                 'FAQ the questions. A text page shows the text below.')
    body = fields.Html(string='Text', sanitize=True)
    url = fields.Char(compute='_compute_url', string='Opens at')

    _slug_unique = models.Constraint('unique(site_id, slug)', 'Each page on a website needs its own web address.')

    @api.depends('slug')
    def _compute_url(self):
        for page in self:
            page.url = f'/page/{page.slug}' if page.slug else ''

    @api.onchange('name')
    def _onchange_name_slug(self):
        if self.name and not self.slug:
            self.slug = self._slugify(self.name)

    @api.model
    def _slugify(self, text):
        return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')[:60] or 'page'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['slug'] = self._slugify(vals.get('slug') or vals.get('name'))
        return super().create(vals_list)

    def write(self, vals):
        if 'slug' in vals:
            vals['slug'] = self._slugify(vals['slug'])
        return super().write(vals)

    def _serialize(self):
        self.ensure_one()
        return {'title': self.name, 'slug': self.slug, 'column': self.column, 'kind': self.kind,
                'body': str(self.body or '') if self.kind == 'text' else ''}
