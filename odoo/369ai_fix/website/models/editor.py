# -*- coding: utf-8 -*-
"""The Fix Website editor (static/src/website/editor/): the Home page, the Services page and
the Info pages drawn the way the site draws them, with a panel on the right to edit the part
you click. One load gives the editor everything; edits go straight to the records (write,
create, unlink, web_resequence) from the browser, batched a moment after typing stops."""
from odoo import api, fields, models

from .home import KINDS
from .site_popups import POPUP_FIELDS


class OnlineServiceSite(models.Model):
    _inherit = 'online.service.site'

    SITE_FIELDS = (
        'name', 'tagline', 'contact_phone', 'contact_whatsapp', 'contact_email', 'contact_address', 'opening_hours',
        'since_year', 'social_facebook', 'social_instagram', 'header_cta', 'header_cta_link',
        'footer_about', 'footer_copyright', 'footer_credit',
        'svc_eyebrow', 'svc_title', 'svc_title2', 'svc_lead', 'svc_modes_eyebrow', 'svc_modes_title', 'svc_fee_label',
        'cov_eyebrow', 'cov_title', 'cov_trust', 'public_url', 'show_device_photos', 'drawing_style',
    ) + POPUP_FIELDS
    ITEM_FIELDS = ('kind', 'sequence', 'active', 'name', 'name2', 'text', 'text2', 'code', 'icon', 'color', 'color2', 'link', 'category_id',
                   'chance', 'month_limit', 'valid_days', 'free_visit')

    @api.model
    def fix_editor_pictures(self, what):
        """The Brand Logos / Service Pictures editors: every brand with its logo, or every repair
        service with its photos."""
        self._fix_check_editor()
        if what == 'brands':
            return [{'id': b.id, 'name': b.name, 'caption': b.web_caption or '', 'color': b.web_color or '',
                     'logo': b._fix_logo_url() if b.web_has_logo else False, 'in_strip': bool(b.web_in_strip)}
                    for b in self.env['device.brand'].search([], order='name')]
        out = []
        for p in self.env['product.template'].search([('repair_category_ids', '!=', False)], order='name'):
            photos = [{'id': img.id, 'name': img.name, 'url': img._web_url('image_512'), 'shown': img == p.web_photo_id}
                      for img in p.web_photo_ids]
            out.append({'id': p.id, 'name': p.name, 'device': ', '.join(p.repair_category_ids.mapped('name')),
                        'model': p.device_model_id.name or p.device_brand_id.name or '', 'price': p.list_price,
                        'most_booked': bool(p.web_most_booked), 'photo': p._fix_photo_url() if p.web_photo_id else False,
                        'photos': photos})
        return out

    @api.model
    def fix_editor_load(self, site_id=False, page_id=False):
        """Everything the editor draws, for one website."""
        self._fix_check_editor()
        sites = self.search([('active', '=', True)])
        site = sites.filtered(lambda s: s.id == site_id)[:1] or sites[:1]
        if not site:
            return {'sites': [], 'site_id': False}
        Page = self.env['fix.home.page'].with_context(active_test=False)
        pages = Page.search([('site_id', '=', site.id)])
        page = pages.filtered(lambda p: p.id == page_id)[:1] or site._fix_live_home_page() or pages[:1]
        everyday = pages.filtered('is_current')[:1] or page
        # As the site words it (src/data/site.ts): a repair without a price (0) shows "Price after
        # check"; {price} in texts becomes the visit fee, or "price after check" when none is set.
        fee = site._fix_visit_fee()
        price = f'OMR {fee:g}' if fee > 0 else 'price after check'
        Cat = self.env['device.category']
        cats = Cat.search([], order='web_home_sequence, id')
        Brand = self.env['device.brand']
        return {
            'sites': [{'id': s.id, 'name': s.name} for s in sites],
            'site_id': site.id,
            'site': {f: self._fix_val(site, f) for f in self.SITE_FIELDS},
            'links': [self._fix_row(l, ('kind', 'name', 'link', 'active', 'sequence')) for l in site.with_context(active_test=False).link_ids.sorted('sequence')],
            'branches': [self._fix_row(b, ('name', 'address', 'phones', 'map_query', 'hours', 'active', 'sequence'))
                         for b in site.with_context(active_test=False).branch_ids.sorted('sequence')],
            'home': {
                'pages': [{'id': p.id, 'name': p.name, 'state': p.state, 'state_note': p.state_note, 'is_current': p.is_current,
                           'starts_on': fields.Datetime.to_string(p.starts_on) if p.starts_on else '',
                           'ends_on': fields.Datetime.to_string(p.ends_on) if p.ends_on else '', 'active': p.active} for p in pages],
                'page_id': page.id if page else False,
                'sections': [self._fix_section(s) for s in page.with_context(active_test=False).section_ids.sorted('sequence')] if page else [],
                'kinds': [{'key': k, 'name': n} for k, n in KINDS],
            },
            'flow': self._fix_section(everyday.with_context(active_test=False).section_ids.filtered(lambda s: s.kind == 'modes')[:1]) if everyday else False,
            'tiles': [{'id': c.id, 'name': c.name, 'show': bool(c.web_show_home), 'sequence': c.web_home_sequence,
                       'image': (c._fix_photo_url() if site.show_device_photos and c.web_photo_id else c._fix_drawing_url(site.drawing_style or '3d'))}
                      for c in cats],
            'brands': [{'id': b.id, 'name': b.name, 'caption': b.web_caption or '', 'logo': b._fix_logo_url() if b.web_has_logo else False}
                       for b in Brand.search([('web_in_strip', '=', True)], order='name')],
            'most_booked': [{'id': p.id, 'name': p.name, 'price': p.list_price, 'device': ', '.join(p.repair_category_ids.mapped('name')),
                             'sequence': p.web_home_sequence or 0, 'image': p._fix_photo_url() if p.web_photo_id else False}
                            for p in self.env['product.template'].search([('web_most_booked', '=', True)], order='web_home_sequence, id')],
            'zones': [dict(self._fix_row(z, ('mode', 'name', 'active', 'sequence', 'latitude', 'longitude')),
                           areas=[self._fix_row(a, ('name', 'sequence', 'latitude', 'longitude')) for a in z.area_ids.sorted('sequence')])
                      for z in site.with_context(active_test=False).zone_ids.sorted('sequence')],
            'faqs': [self._fix_row(f, ('name', 'answer', 'active', 'sequence')) for f in site.with_context(active_test=False).faq_ids.sorted('sequence')],
            'pages': [self._fix_row(p, ('name', 'slug', 'column', 'kind', 'active', 'sequence', 'body'))
                      for p in site.with_context(active_test=False).page_ids.sorted('sequence')],
            # Pop-ups & chat: the four lists (wheel prizes, chat replies, slider slides, leaving tiles)
            'items': [self._fix_row(i, self.ITEM_FIELDS) for i in site.with_context(active_test=False).item_ids.sorted('sequence')],
            'hours': site.opening_hours or '',
            'price': price, 'visit_fee': fee, 'price_later': 'Price after check',
            'totals': {'categories': len(cats), 'brands': Brand.search_count([]),
                       'models': self.env['device.model'].search_count([]) if 'device.model' in self.env else 0},
            'views': {'page_text': self.env.ref('369ai_fix.view_fix_site_page_text_form').id,
                      'home_page': self.env.ref('369ai_fix.view_fix_home_page_form').id},
        }

    @api.model
    def fix_editor_search_services(self, query):
        """Repair services to add to "Most booked": name match, not already picked."""
        self._fix_check_editor()
        q = (query or '').strip()
        if not q:
            return []
        Product = self.env['product.template']
        found = Product.search([('name', 'ilike', q), ('repair_category_ids', '!=', False), ('web_most_booked', '=', False)],
                               order='name', limit=20)
        return [{'id': p.id, 'name': p.name, 'device': ', '.join(p.repair_category_ids.mapped('name')),
                 'model': p.device_model_id.name or p.device_brand_id.name or ''} for p in found]

    @api.model
    def _fix_val(self, rec, field):
        v = rec[field]
        if isinstance(v, models.BaseModel):
            return v.id
        return v if v is not False and v is not None else ('' if rec._fields[field].type in ('char', 'text', 'html') else v)

    @api.model
    def _fix_row(self, rec, names):
        out = {'id': rec.id}
        for f in names:
            out[f] = self._fix_val(rec, f)
        return out

    @api.model
    def _fix_section(self, s):
        if not s:
            return False
        out = self._fix_row(s, ('kind', 'name', 'active', 'sequence', 'eyebrow', 'title', 'title2', 'subtitle', 'text',
                                'button1', 'button1_link', 'button2', 'button2_link', 'badge', 'video_url'))
        out['name'] = dict(KINDS).get(s.kind, s.name)
        out['image'] = s._fix_image_url('image_512') if s.image_1920 else False
        out['lines'] = []
        for l in s.with_context(active_test=False).line_ids.sorted('sequence'):
            row = self._fix_row(l, ('name', 'value', 'text', 'extra', 'stars', 'link', 'active', 'sequence', 'body', 'role'))
            row['image'] = f'/web/image/fix.home.line/{l.id}/image_256?unique={int(l.write_date.timestamp())}' if l.image_1920 else False
            out['lines'].append(row)
        return out
