# -*- coding: utf-8 -*-
"""Everything on every page of the website, edited on the Website record (Website Details):
name and tagline, contact details, the header menu, the branches, the footer and the
Services page wording. Coverage areas, FAQs and info pages are in site_pages.py. Plus the
tick-boxes in the catalogue that feed the home page: device types "Show on home", brands
"In the brands strip", repair services "Most booked".

``online.service.order.website_content(host)`` hands all of it to the website together with
the live home page (see home.py). The website keeps a copy for five minutes and keeps the
last copy when Odoo is unreachable, so nothing here can take the site down.
"""
from odoo import api, fields, models


class OnlineServiceSite(models.Model):
    _inherit = 'online.service.site'

    tagline = fields.Char(help='Under the name in the browser tab and the footer, e.g. "Electronics repair at your doorstep".')
    contact_phone = fields.Char(string='Phone', help='Shown as typed, e.g. +968 7832 3116.')
    contact_whatsapp = fields.Char(string='WhatsApp number', help='Digits only with the country code, e.g. 96878323116. Every "WhatsApp us" button opens this number.')
    contact_email = fields.Char(string='Email')
    contact_address = fields.Text(string='Address')
    opening_hours = fields.Char(string='Opening hours', help='e.g. Sat–Thu 9:00–21:00')
    since_year = fields.Char(string='Since (year)', help='e.g. 2003 — used in "since 2003" on the site.')
    social_facebook = fields.Char(string='Facebook')
    social_instagram = fields.Char(string='Instagram')
    header_cta = fields.Char(string='Header button', help='The orange button in the top bar, e.g. "Book a repair".')
    header_cta_link = fields.Char(string='Header button opens', default='/services#catalog')
    link_ids = fields.One2many('fix.site.link', 'site_id', string='Links')
    branch_ids = fields.One2many('fix.site.branch', 'site_id', string='Branches')
    footer_about = fields.Text(string='About text', help='The paragraph under the logo in the footer.')
    footer_copyright = fields.Char(string='Copyright line', help='{year} is replaced by the current year.')
    footer_credit = fields.Char(string='Credit line', help='e.g. "Site developed by Alphalize". Empty = none.')
    home_page_ids = fields.One2many('fix.home.page', 'site_id', string='Home pages')
    home_page_count = fields.Integer(compute='_compute_home_page_count')
    # Services page wording (the repair flow itself is the home page's "How we fix it" section)
    svc_eyebrow = fields.Char(string='Small heading', help='Above the title, e.g. "Services".')
    svc_title = fields.Char(string='Title', help='e.g. "Doorstep repair,"')
    svc_title2 = fields.Char(string='Title (green part)', help='e.g. "on the spot or in our lab."')
    svc_lead = fields.Text(string='Intro', help='Under the title. The site adds the counts (device types, brands, models) after it.')
    svc_modes_eyebrow = fields.Char(string='Flow small heading', help='e.g. "How it works"')
    svc_modes_title = fields.Char(string='Flow title', help='e.g. "We come to you first"')
    svc_fee_label = fields.Char(string='Fee label', help='Under the repair flow, before the price, e.g. "Visit fee".')
    cov_eyebrow = fields.Char(string='Coverage small heading', help='e.g. "Check your area"')
    cov_title = fields.Char(string='Coverage title', help='e.g. "Where we cover"')
    cov_trust = fields.Text(string='Trust points', help='Under the areas, one per line. {price} becomes the visit fee (e.g. OMR 5), or "price after check" when none is set.')
    zone_ids = fields.One2many('fix.coverage.zone', 'site_id', string='Coverage zones')
    faq_ids = fields.One2many('fix.site.faq', 'site_id', string='FAQs')
    page_ids = fields.One2many('fix.site.page', 'site_id', string='Info pages')

    def _compute_home_page_count(self):
        for site in self:
            site.home_page_count = len(site.home_page_ids)

    def _fix_live_home_page(self):
        """The home page the website shows now: a dated page inside its dates, else the
        everyday page, else any page."""
        self.ensure_one()
        Page = self.env['fix.home.page']
        now = fields.Datetime.now()
        dated = Page.search([('site_id', '=', self.id),
                             '|', ('starts_on', '!=', False), ('ends_on', '!=', False),
                             '|', ('starts_on', '=', False), ('starts_on', '<=', now),
                             '|', ('ends_on', '=', False), ('ends_on', '>=', now)],
                            order='starts_on desc, id desc', limit=1)
        if dated:
            return dated
        return (Page.search([('site_id', '=', self.id), ('is_current', '=', True)], limit=1)
                or Page.search([('site_id', '=', self.id)], limit=1))

    def action_fix_home_pages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'Home page', 'res_model': 'fix.home.page',
            'view_mode': 'list,form', 'domain': [('site_id', '=', self.id)],
            'context': {'default_site_id': self.id, 'active_test': False},
        }

    def action_fix_load_starter_content(self):
        """Fill the empty places (contact, links, branches, footer, a first home page) with
        the website's texts as they were in code. Nothing already typed is overwritten."""
        from ..seed import load_starter_content
        made = load_starter_content(self.env, sites=self)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'title': 'Starter content loaded',
                       'message': 'Empty places filled.' + (' A home page was made.' if made else ''), 'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _fix_site_content(self):
        """The website's name, contact details, header, branches and footer, plus the pop-ups,
        wheel, chat assistant and slider (site_popups.py)."""
        self.ensure_one()
        links = self.link_ids.sorted('sequence')
        out = self._fix_popups()
        out.update({
            'name': self.name, 'tagline': self.tagline or '',
            'phone': self.contact_phone or '', 'whatsapp': self.contact_whatsapp or '',
            'email': self.contact_email or '', 'address': self.contact_address or '',
            'hours': self.opening_hours or '', 'since': self.since_year or '',
            'visit_fee': self._fix_visit_fee(),
            'social': {'facebook': self.social_facebook or '', 'instagram': self.social_instagram or ''},
            'header': {'cta': self.header_cta or '', 'cta_link': self.header_cta_link or '',
                       'menu': [{'label': l.name, 'link': l.link} for l in links if l.kind == 'header' and l.active]},
            'quick_links': [{'label': l.name, 'link': l.link} for l in links if l.kind == 'quick' and l.active],
            'branches': [b._serialize() for b in self.branch_ids.sorted('sequence') if b.active],
            'footer': {'about': self.footer_about or '', 'copyright': self.footer_copyright or '',
                       'credit': self.footer_credit or ''},
            'services': {'eyebrow': self.svc_eyebrow or '', 'title': self.svc_title or '', 'title2': self.svc_title2 or '',
                         'lead': self.svc_lead or '', 'modes_eyebrow': self.svc_modes_eyebrow or '',
                         'modes_title': self.svc_modes_title or '', 'fee_label': self.svc_fee_label or ''},
            'coverage': self._fix_coverage(),
            'faq': [{'q': f.name, 'a': f.answer or ''} for f in self.faq_ids.sorted('sequence') if f.active],
            'pages': [p._serialize() for p in self.page_ids.sorted('sequence') if p.active],
        })
        return out

    def _fix_visit_fee(self):
        """The visit fee product's sale price (Repair settings: mobile_repair.inspection_charge_product_id,
        "Inspection / Visit Fee"). 0 when none is set: the site then says "price after check"."""
        param = self.env['ir.config_parameter'].sudo().get_param('mobile_repair.inspection_charge_product_id')
        if not param or not str(param).isdigit():
            return 0
        fee = self.env['product.product'].sudo().browse(int(param)).exists()
        return fee.lst_price if fee else 0

    def _fix_coverage(self):
        """Doorstep and pickup zones with their areas, and every area's map position (the
        site's "check my location" finds the nearest one)."""
        self.ensure_one()
        zones = self.zone_ids.filtered('active').sorted('sequence')
        geo = {}
        for area in zones.area_ids:
            if area.latitude or area.longitude:
                geo.setdefault(area.name, [area.latitude, area.longitude])
        return {
            'eyebrow': self.cov_eyebrow or '', 'title': self.cov_title or '',
            'trust': [x.strip() for x in (self.cov_trust or '').splitlines() if x.strip()],
            'doorstep': {'zones': [z._serialize() for z in zones if z.mode == 'doorstep']},
            'pickup': {'zones': [z._serialize() for z in zones if z.mode == 'pickup']},
            'geo': geo,
        }

    def _fix_mode_cards(self):
        """The doorstep / pickup cards of the live home page (else the everyday page), shown
        on the Services page too, even when the home page hides them. First card = Doorstep,
        second = Pickup."""
        self.ensure_one()
        Section = self.env['fix.home.section']
        for page in (self._fix_live_home_page(), self.home_page_ids.filtered('is_current')[:1]):
            if not page:
                continue
            section = Section.with_context(active_test=False).search(
                [('page_id', '=', page.id), ('kind', '=', 'modes')], order='active desc, sequence', limit=1)
            lines = section.line_ids.filtered('active').sorted('sequence') if section else False
            if lines:
                return [{'title': l.name or '', 'short': l.extra or '', 'eta': l.value or '',
                         'steps': [x.strip() for x in (l.text or '').splitlines() if x.strip()]} for l in lines]
        return []

    def action_fix_coverage(self):
        return self._fix_site_action('fix.coverage.zone', 'Coverage Areas')

    def action_fix_faqs(self):
        return self._fix_site_action('fix.site.faq', 'FAQs')

    def action_fix_pages(self):
        return self._fix_site_action('fix.site.page', 'Info Pages')

    def _fix_site_action(self, model, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': name, 'res_model': model, 'view_mode': 'list,form',
            'domain': [('site_id', '=', self.id)], 'context': {'default_site_id': self.id, 'active_test': False},
        }


class FixSiteLink(models.Model):
    _name = 'fix.site.link'
    _description = 'Website menu link'
    _order = 'kind, sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade')
    kind = fields.Selection([('header', 'Header menu'), ('quick', 'Footer quick links')], required=True, default='header')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Label', required=True)
    link = fields.Char(string='Opens', required=True, help='A page on the site (/services) or a full web address.')


class FixSiteBranch(models.Model):
    _name = 'fix.site.branch'
    _description = 'Website branch (footer and contact page)'
    _order = 'sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Branch', required=True, help='e.g. Ruwi')
    address = fields.Text(string='Address', help='One line per row, as it should read on the site.')
    phones = fields.Char(string='Phones', help='Comma-separated, e.g. +968 9792 3077, +968 9792 2924')
    map_query = fields.Char(string='Map search', help='What Google Maps should search for, e.g. "Computer Street, Ruwi, Muscat, Oman".')
    hours = fields.Char(string='Opening hours')

    def _serialize(self):
        self.ensure_one()
        return {
            'name': self.name, 'lines': [x.strip() for x in (self.address or '').splitlines() if x.strip()],
            'phones': [x.strip() for x in (self.phones or '').split(',') if x.strip()],
            'map': self.map_query or '', 'hours': self.hours or '',
        }


class DeviceCategory(models.Model):
    _inherit = 'device.category'

    web_show_home = fields.Boolean(string='Show on home', default=True,
                                   help='A tile in "What can we fix for you?" on the home page.')


class DeviceBrand(models.Model):
    _inherit = 'device.brand'

    web_in_strip = fields.Boolean(string='In the brands strip', default=True,
                                  help='Shown in the moving row of brand logos on the home page.')
    web_caption = fields.Char(string='Caption', help='Under the logo in the brands strip, e.g. "iPhone · iPad · Mac".')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    web_most_booked = fields.Boolean(string='Most booked', help='Shown in "Most booked repairs" on the home page.')
    web_home_sequence = fields.Integer(string='Home order', default=10)


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    @api.model
    def website_content(self, host):
        """The website's texts: site details, header, footer, branches and the live home page."""
        self._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        if not site:
            return {'ok': False, 'error': 'unknown website'}
        page = site._fix_live_home_page()
        Cat = self.env['device.category']
        tiles = [{'id': c.id, 'name': c.name} for c in Cat.search([('web_show_home', '=', True)], order='id')]
        Brand = self.env['device.brand']
        strip = [{'id': b.id, 'name': b.name, 'caption': b.web_caption or '', 'color': b.web_color or '',
                  'logo': b._fix_logo_url() if b.web_has_logo else False}
                 for b in Brand.search([('web_in_strip', '=', True)], order='name')]
        picks = [{'id': p.id, 'name': p.name, 'price': p.list_price,
                  'categories': p.repair_category_ids.mapped('name'),
                  'image': p._fix_photo_url() if p.web_photo_id else False}
                 for p in self.env['product.template'].search([('web_most_booked', '=', True)], order='web_home_sequence, id')]
        return {
            'ok': True,
            'site': site._fix_site_content(),
            'home': page._serialize() if page else {'sections': []},
            'tiles': tiles, 'brands': strip, 'most_booked': picks,
            'modes': site._fix_mode_cards(),
        }

    @api.model
    def website_catalog(self, host):
        """Also tell the website which device types are on the home page, which repairs
        are "most booked" and each repair's line under its name (its Sales Description),
        so it can draw them from the catalogue it already has."""
        data = super().website_catalog(host)
        if data.get('ok'):
            for cat in data.get('categories', []):
                c = self.env['device.category'].browse(cat['id'])
                cat['show_home'] = bool(c.web_show_home)
                for sv in cat.get('services', []):   # the catalogue lists product variants
                    p = self.env['product.product'].browse(sv['id']).product_tmpl_id
                    sv['most_booked'] = bool(p.web_most_booked)
                    sv['home_sequence'] = p.web_home_sequence or 0
                    sv['caption'] = (p.description_sale or '').strip()
        return data
