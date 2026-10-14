# -*- coding: utf-8 -*-
"""The website's home page, edited here instead of in code.

A *home page* is a saved version: the everyday one, or a dated one (an Eid offer that
shows itself between two dates and then hands back). A page is a list of *sections*,
top to bottom the way the visitor scrolls: hero, services, service modes, brands strip,
reviews, milestones, partners, closing banner. Each section can be switched off or
dragged into another place, and holds its own wording, pictures and *lines* (the
hero's counters, the mode cards, the reviews, the milestones, the partner logos, the
trust points). The website asks for the live page through
``online.service.order.website_content`` and shows it within five minutes.

Device tiles and "most booked" repairs are not lines here: they are the device
categories and repair services ticked "Show on home" in the catalogue.
"""
from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

KINDS = [
    ('hero', 'Top banner'),
    ('services', 'What we fix (device tiles + most booked)'),
    ('modes', 'Doorstep / pickup cards'),
    ('brands', 'Brands strip'),
    ('reviews', 'Customer reviews'),
    ('milestones', 'Our journey'),
    ('partners', 'Partners'),
    ('cta', 'Closing banner'),
]
KIND_ORDER = [k for k, _l in KINDS]

# What the lines of each kind of section are, for the form's labels and the preview.
LINES = {
    'hero': ('Counters', 'Number', 'Label'),
    'modes': ('Cards', 'Title', 'Steps (one per line)'),
    'reviews': ('Reviews', 'Customer', 'Review'),
    'milestones': ('Milestones', 'Title', 'Text'),
    'partners': ('Partner logos', 'Partner', ''),
    'cta': ('Trust points', 'Point', ''),
}


class FixHomePage(models.Model):
    _name = 'fix.home.page'
    _description = 'Website home page (a saved version)'
    _order = 'is_current desc, starts_on desc, id'

    name = fields.Char(required=True, help='What this page is for: "Everyday page", "Eid offer 2027"…')
    note = fields.Char(help='A reminder for staff; the website never shows it.')
    site_id = fields.Many2one('online.service.site', string='Website', required=True, ondelete='cascade',
                              default=lambda self: self.env['online.service.site'].search([], limit=1))
    active = fields.Boolean(default=True)
    is_current = fields.Boolean(string='Everyday page', copy=False,
                                help='The page the website shows when no dated page is running. One per website.')
    starts_on = fields.Datetime(string='Show from', help='Leave both dates empty for the everyday page.')
    ends_on = fields.Datetime(string='Show until')
    section_ids = fields.One2many('fix.home.section', 'page_id', string='Sections', copy=True)
    section_count = fields.Integer(compute='_compute_state')
    state = fields.Selection([('live', 'Live now'), ('scheduled', 'Scheduled'), ('ended', 'Ended'), ('off', 'Not shown')],
                             compute='_compute_state', string='Status')
    state_note = fields.Char(compute='_compute_state', string='Because')

    @api.depends('is_current', 'starts_on', 'ends_on', 'active', 'section_ids', 'site_id')
    def _compute_state(self):
        now = fields.Datetime.now()
        for page in self:
            page.section_count = len(page.section_ids)
            live = page.site_id and page.site_id._fix_live_home_page()
            if not page.active:
                page.state, page.state_note = 'off', _('Archived')
            elif live and live.id == page.id:
                page.state = 'live'
                page.state_note = _('Dated page running') if (page.starts_on or page.ends_on) else _('Everyday page')
            elif page.starts_on and page.starts_on > now:
                page.state, page.state_note = 'scheduled', _('Starts %s', fields.Datetime.to_string(page.starts_on))
            elif page.ends_on and page.ends_on < now:
                page.state, page.state_note = 'ended', _('Ended %s', fields.Datetime.to_string(page.ends_on))
            elif page.is_current:
                page.state, page.state_note = 'off', _('A dated page is running instead')
            else:
                page.state, page.state_note = 'off', _('Not the everyday page and no dates')

    @api.constrains('starts_on', 'ends_on')
    def _check_dates(self):
        for page in self:
            if page.starts_on and page.ends_on and page.ends_on <= page.starts_on:
                raise UserError(_('"Show until" must be after "Show from".'))

    def _keep_one_current(self):
        """Switching a page on as the everyday page switches the website's other pages off."""
        for page in self.filtered('is_current'):
            others = self.search([('site_id', '=', page.site_id.id), ('is_current', '=', True), ('id', '!=', page.id)])
            others.with_context(fix_settling=True).write({'is_current': False})

    @api.model_create_multi
    def create(self, vals_list):
        pages = super().create(vals_list)
        pages._keep_one_current()
        return pages

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_current') and not self.env.context.get('fix_settling'):
            self._keep_one_current()
        return res

    def unlink(self):
        for page in self:
            if page.is_current and self.search_count([('site_id', '=', page.site_id.id), ('id', '!=', page.id)]):
                raise UserError(_('Make another page the everyday page first, then delete this one.'))
        return super().unlink()

    def action_make_current(self):
        self.ensure_one()
        self.write({'is_current': True, 'starts_on': False, 'ends_on': False})

    def action_duplicate(self):
        self.ensure_one()
        copy = self.copy({'name': _('%s (copy)', self.name), 'is_current': False, 'starts_on': False, 'ends_on': False})
        return {'type': 'ir.actions.act_window', 'res_model': 'fix.home.page', 'res_id': copy.id, 'view_mode': 'form'}

    def action_open_website(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.site_id.public_url or '/', 'target': 'new'}

    def _serialize(self):
        """What the website receives: the sections that are switched on, in order."""
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name,
            'sections': [s._serialize() for s in self.section_ids.sorted('sequence') if s.active],
        }


class FixHomeSection(models.Model):
    _name = 'fix.home.section'
    _description = 'Website home page section'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    page_id = fields.Many2one('fix.home.page', required=True, ondelete='cascade', string='Home page')
    site_id = fields.Many2one(related='page_id.site_id', store=True)
    sequence = fields.Integer(default=10, help='Drag the rows to change the order on the website: top to bottom.')
    active = fields.Boolean(string='Shown', default=True, help='Off: this section disappears from the website. Nothing is deleted.')
    kind = fields.Selection(KINDS, required=True, default='hero')
    name = fields.Char(string='Section', compute='_compute_name', store=True)

    # wording — each kind uses the ones its form shows
    eyebrow = fields.Char(string='Small heading', help='The short line above the title, e.g. "Doorstep electronics repair · Oman".')
    title = fields.Char(string='Title')
    title2 = fields.Char(string='Title, coloured part', help='The part of the title shown in the accent colour, e.g. "Fixed Right."')
    subtitle = fields.Char(string='Line under the title')
    text = fields.Text(string='Text')
    button1 = fields.Char(string='Button')
    button1_link = fields.Char(string='Button opens', help='A page on the site (/services#catalog) or a full web address.')
    button2 = fields.Char(string='Second button')
    button2_link = fields.Char(string='Second button opens', help='Empty = opens WhatsApp with the website\'s number.')
    badge = fields.Char(string='Badge', help='"What we fix": the small pill above the title. Empty = "N services · doorstep & pickup".')
    video_url = fields.Char(string='Background video', help='Top banner: the video file on the site, e.g. /media/kling.mp4. Empty = none.')
    image_1920 = fields.Image(string='Picture', max_width=1920, max_height=1920,
                              help='Top banner: the still picture shown before the video plays. Partners/others: not used.')

    line_ids = fields.One2many('fix.home.line', 'section_id', string='Lines', copy=True)
    line_label = fields.Char(compute='_compute_line_labels')
    line_name_label = fields.Char(compute='_compute_line_labels')
    line_text_label = fields.Char(compute='_compute_line_labels')
    preview_html = fields.Html(compute='_compute_preview', sanitize=False, string='How it looks')

    @api.depends('kind', 'title')
    def _compute_name(self):
        labels = dict(KINDS)
        for s in self:
            s.name = labels.get(s.kind, s.kind)

    @api.depends('kind')
    def _compute_line_labels(self):
        for s in self:
            lab = LINES.get(s.kind, ('Lines', 'Name', 'Text'))
            s.line_label, s.line_name_label, s.line_text_label = lab

    @api.depends('kind', 'eyebrow', 'title', 'title2', 'subtitle', 'text', 'button1', 'button2', 'badge',
                 'line_ids.name', 'line_ids.text', 'line_ids.value', 'line_ids.active', 'active')
    def _compute_preview(self):
        for s in self:
            e = escape
            parts = []
            if s.eyebrow:
                parts.append(f'<div style="font:700 11px sans-serif;letter-spacing:.1em;text-transform:uppercase;color:#1d4ed8">{e(s.eyebrow)}</div>')
            if s.badge and s.kind == 'services':
                parts.append(f'<span style="display:inline-block;font:600 11px sans-serif;background:#e8efff;color:#1d4ed8;border-radius:999px;padding:3px 10px">{e(s.badge)}</span>')
            if s.title or s.title2:
                parts.append(f'<div style="font:800 22px/1.15 sans-serif;margin:4px 0">{e(s.title or "")} <span style="color:#1d4ed8">{e(s.title2 or "")}</span></div>')
            if s.subtitle:
                parts.append(f'<div style="color:#44546c;font:14px sans-serif">{e(s.subtitle)}</div>')
            if s.text:
                parts.append(f'<p style="color:#44546c;font:13px sans-serif;max-width:60ch">{e(s.text)}</p>')
            btns = [b for b in (s.button1, s.button2) if b]
            if btns:
                parts.append('<div>' + ''.join(
                    f'<span style="display:inline-block;margin:6px 6px 0 0;padding:7px 14px;border-radius:999px;background:{"#f97316" if i == 0 else "#25d366"};color:#fff;font:700 13px sans-serif">{e(b)}</span>'
                    for i, b in enumerate(btns)) + '</div>')
            lines = s.line_ids.filtered('active').sorted('sequence')
            if s.kind == 'hero' and lines:
                parts.append('<div style="display:flex;gap:18px;margin-top:10px">' + ''.join(
                    f'<div><b style="font:800 18px sans-serif">{e(l.value or "")}</b><br><small style="color:#8593a8">{e(l.name or "")}</small></div>' for l in lines) + '</div>')
            elif s.kind == 'services':
                tiles = self.env['device.category'].search([('web_show_home', '=', True)], order='id')
                parts.append('<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">' + ''.join(
                    f'<span style="background:#e8efff;border-radius:10px;padding:8px 10px;font:600 12px sans-serif">{e(c.name)}</span>' for c in tiles) + '</div>')
                picks = self.env['product.template'].search([('web_most_booked', '=', True)], order='web_home_sequence, id')
                parts.append(f'<div style="color:#8593a8;font:12px sans-serif;margin-top:6px">Most booked: {e(", ".join(picks.mapped("name")) or "none ticked yet")}</div>')
            elif s.kind == 'modes':
                parts.append('<div style="display:flex;gap:10px;margin-top:8px">' + ''.join(
                    f'<div style="flex:1;border:1px solid #dde3ec;border-radius:12px;padding:10px"><b style="font:700 14px sans-serif">{e(l.name or "")}</b><div style="color:#44546c;font:12px sans-serif">{e(l.value or "")}</div><ol style="margin:6px 0 0;padding-left:18px;font:12px sans-serif;color:#44546c">{"".join(f"<li>{e(x.strip())}</li>" for x in (l.text or "").splitlines() if x.strip())}</ol></div>' for l in lines) + '</div>')
            elif s.kind == 'brands':
                brands = self.env['device.brand'].search([('web_in_strip', '=', True)], order='name')
                parts.append('<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">' + ''.join(
                    f'<span style="border:1px solid #dde3ec;border-radius:8px;padding:6px 10px;font:800 13px sans-serif">{e(b.name)}</span>' for b in brands) + '</div>'
                    + f'<div style="color:#8593a8;font:12px sans-serif;margin-top:6px">{len(brands)} brands ticked "In the brands strip"</div>')
            elif s.kind == 'reviews':
                parts.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">' + ''.join(
                    f'<div style="border:1px solid #dde3ec;border-radius:12px;padding:10px;font:12px sans-serif"><span style="color:#f59e0b">{"★" * (l.stars or 0)}</span><div>{e(l.text or "")}</div><b>{e(l.name or "")}</b> <small style="color:#8593a8">{e(l.value or "")}</small></div>' for l in lines[:4]) + '</div>')
            elif s.kind == 'milestones':
                parts.append('<ol style="margin:8px 0 0;padding-left:18px;font:13px sans-serif">' + ''.join(
                    f'<li><b>{e(l.value or "")}</b> {e(l.name or "")} <span style="color:#8593a8">{e(l.text or "")}</span></li>' for l in lines) + '</ol>')
            elif s.kind == 'partners':
                parts.append('<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">' + ''.join(
                    (f'<img src="data:image/png;base64,{l.image_128.decode()}" style="height:36px" alt=""/>' if l.image_128 else
                     f'<span style="border:1px solid #dde3ec;border-radius:8px;padding:8px 12px;font:800 13px sans-serif">{e(l.name or "")}</span>') for l in lines) + '</div>')
            elif s.kind == 'cta' and lines:
                parts.append('<div style="color:#44546c;font:12px sans-serif;margin-top:8px">' + ' · '.join(f'✓ {e(l.name or "")}' for l in lines) + '</div>')
            dim = '' if s.active else 'opacity:.45;'
            s.preview_html = (f'<div style="{dim}border:1px solid #dde3ec;border-radius:14px;padding:16px;background:#fff">'
                              + ''.join(parts) + ('' if s.active else '<div style="color:#b45309;font:600 12px sans-serif;margin-top:8px">Hidden on the website</div>') + '</div>')

    def action_toggle_active(self):
        for s in self:
            s.active = not s.active

    def _serialize(self):
        self.ensure_one()
        lines = [l._serialize() for l in self.line_ids.sorted('sequence') if l.active]
        out = {
            'kind': self.kind, 'eyebrow': self.eyebrow or '', 'title': self.title or '', 'title2': self.title2 or '',
            'subtitle': self.subtitle or '', 'text': self.text or '', 'badge': self.badge or '',
            'button1': self.button1 or '', 'button1_link': self.button1_link or '',
            'button2': self.button2 or '', 'button2_link': self.button2_link or '',
            'lines': lines,
        }
        if self.kind == 'hero':
            out['video'] = self.video_url or ''
            out['poster'] = self._fix_image_url('image_1920') if self.image_1920 else False
        return out

    def _fix_image_url(self, field):
        self.ensure_one()
        return f'/web/image/fix.home.section/{self.id}/{field}?unique={int(self.write_date.timestamp())}'

    def _can_return_content(self, field_name=None, access_token=None):
        if field_name in ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128'):
            return True
        return super()._can_return_content(field_name=field_name, access_token=access_token)


class FixHomeLine(models.Model):
    _name = 'fix.home.line'
    _description = 'Website home page section line'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    section_id = fields.Many2one('fix.home.section', required=True, ondelete='cascade')
    kind = fields.Selection(related='section_id.kind')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Name', help='Counter label · card title · customer name · milestone title · partner · trust point')
    value = fields.Char(string='Value', help='Counter number · card arrival line · customer area · milestone year')
    text = fields.Text(string='Text', help='Card steps (one per line) · review text · milestone text')
    extra = fields.Char(string='Extra', help='Card short line · review service')
    stars = fields.Integer(string='Stars', default=5)
    link = fields.Char(string='Opens', help='Partner: optional web address')
    image_1920 = fields.Image(string='Logo', max_width=1024, max_height=1024)

    def _serialize(self):
        self.ensure_one()
        out = {'name': self.name or '', 'value': self.value or '', 'text': self.text or '', 'extra': self.extra or '',
               'stars': self.stars, 'link': self.link or ''}
        if self.image_1920:
            out['image'] = f'/web/image/fix.home.line/{self.id}/image_512?unique={int(self.write_date.timestamp())}'
        return out

    def _can_return_content(self, field_name=None, access_token=None):
        if field_name in ('image_1920', 'image_1024', 'image_512', 'image_256', 'image_128'):
            return True
        return super()._can_return_content(field_name=field_name, access_token=access_token)
