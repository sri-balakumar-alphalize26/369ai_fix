# -*- coding: utf-8 -*-
"""Pop-ups & chat: the last website texts that used to live in code, now on the Website
record: the announcement bar, the welcome pop-up (which one opens first), the flash offer,
the Spin & Win wheel, the chat assistant, the "Book your slot" slider and the "Leaving
already?" panel, and the cookie notice. The four lists (wheel prizes, chat quick replies,
slider slides, leaving-panel tiles) share one model, ``fix.site.item``.

Same rule as every other site field: empty = the website's own wording. Words in curly
brackets ({site}, {code}, {fee}, ...) are sent as typed; the website fills them in.
"""
from odoo import api, fields, models

WELCOME = [('slot', 'Book your slot slider'), ('spin', 'Spin & Win wheel'), ('flash', 'Flash offer'), ('none', 'No welcome pop-up')]
ITEM_KINDS = [('wheel', 'Spin & Win prize'), ('reply', 'Chat quick reply'), ('slide', 'Slider slide'), ('tile', 'Leaving panel tile')]
ICONS = [('diag', 'Magnifier (diagnosis)'), ('pick', 'Scooter (pickup)'), ('clean', 'Sparkle (cleaning)'),
         ('fast', 'Bolt (priority)'), ('data', 'Cloud (backup)'), ('guard', 'Shield (screen guard)')]
INTENTS = [('book', 'Book a repair'), ('area', 'Check my area'), ('price', 'Prices'), ('time', 'How long'),
           ('contact', 'Branches & contact'), ('hours', 'Opening hours'), ('human', 'Talk to a person'), ('menu', 'Back to the menu')]
BOT_ANSWERS = ('book', 'dev', 'iss', 'area', 'price', 'time', 'contact', 'hours', 'human', 'menu', 'found', 'fallback')

# every single-value field of this file, in the order the editor lists them
POPUP_FIELDS = (
    'ann_show', 'ann_text', 'ann_button', 'ann_link', 'ann_speed_s',
    'welcome_popup', 'welcome_delay_ms', 'welcome_flash_delay_ms', 'welcome_snooze_days',
    'flash_badge', 'flash_title', 'flash_body', 'flash_code', 'flash_button', 'flash_button_link',
    'flash_wa_button', 'flash_wa_msg', 'flash_later',
    'cookie_show', 'cookie_title', 'cookie_text', 'cookie_decline', 'cookie_accept', 'cookie_delay_ms',
    'wheel_show', 'wheel_every_days', 'wheel_valid_days',
    'wheel_tab', 'wheel_eyebrow', 'wheel_title', 'wheel_title2', 'wheel_subtitle', 'wheel_spin', 'wheel_later',
    'wheel_won', 'wheel_note', 'wheel_book', 'wheel_wa', 'wheel_wa_msg',
    'bot_name', 'bot_status', 'bot_greeting', 'bot_placeholder', 'bot_tip', 'bot_wa_tip', 'bot_wa_msg',
) + tuple(f'bot_a_{k}' for k in BOT_ANSWERS) + (
    'eng_eyebrow', 'eng_title2', 'eng_perks', 'eng_from_label', 'eng_slide_ms', 'eng_idle_s', 'eng_still_s', 'eng_wa_msg',
    'eng_form_pill', 'eng_form_title', 'eng_form_subtitle', 'eng_form_privacy', 'eng_form_send',
    'eng_form_all', 'eng_form_all_link', 'eng_form_features',
    'exit_title', 'exit_status', 'exit_text', 'exit_button', 'exit_wa_msg', 'exit_tile_msg', 'exit_link', 'exit_link_label',
)


def _lines(text):
    return [x.strip() for x in (text or '').splitlines() if x.strip()]


class OnlineServiceSite(models.Model):
    _inherit = 'online.service.site'

    # announcement bar
    ann_show = fields.Boolean(string='Show the announcement bar', default=True)
    ann_text = fields.Char(string='Bar text', help='e.g. Doorstep repair across Oman — free diagnosis this week')
    ann_button = fields.Char(string='Bar button', help='e.g. Book now →')
    ann_link = fields.Char(string='Bar button opens', help='e.g. /services#catalog')
    ann_speed_s = fields.Integer(string='Scroll time (seconds)', default=30, help='One full pass of the text. Bigger = slower.')
    # welcome pop-up
    welcome_popup = fields.Selection(WELCOME, string='Welcome pop-up', default='slot', required=True,
                                     help='What opens a moment after a visitor arrives.')
    welcome_delay_ms = fields.Integer(string='Opens after (ms)', default=1500)
    welcome_flash_delay_ms = fields.Integer(string='Flash offer opens after (ms)', default=4000)
    welcome_snooze_days = fields.Integer(string='Stay away for (days)', default=30,
                                         help='After the visitor closes it with ×, no welcome pop-up for this many days on that browser.')
    # flash offer
    flash_badge = fields.Char(string='Small red badge', help='e.g. Flash offer')
    flash_title = fields.Char(string='Offer title', help='e.g. Free diagnosis this week')
    flash_body = fields.Text(string='Offer text', help='[Visit fee line] becomes the visit fee line.')
    flash_code = fields.Char(string='Offer code', help='e.g. 369FIX')
    flash_button = fields.Char(string='Green button', help='e.g. Book with offer')
    flash_button_link = fields.Char(string='Green button opens', help='e.g. /services#catalog')
    flash_wa_button = fields.Char(string='Offer WhatsApp button', help='e.g. WhatsApp us')
    flash_wa_msg = fields.Char(string='Offer WhatsApp message', help='[Website name], [Code] = the offer code.')
    flash_later = fields.Char(string='Offer close link', help='e.g. No thanks')
    # cookie notice
    cookie_show = fields.Boolean(string='Show the cookie notice', default=True)
    cookie_title = fields.Char(string='Cookie title', help='e.g. We use cookies')
    cookie_text = fields.Text(string='Cookie text')
    cookie_decline = fields.Char(string='Decline button', help='e.g. Decline')
    cookie_accept = fields.Char(string='Accept button', help='e.g. Accept')
    cookie_delay_ms = fields.Integer(string='Cookie notice after (ms)', default=1200)
    # Spin & Win. Off = the wheel and its gift tab are not on the site, nobody can spin, and a
    # prize already won is not applied to bookings or shown to the technician (the wins stay).
    wheel_show = fields.Boolean(string='Spin & Win', default=True,
                                help='Off: no gift tab, no wheel, no spins, and prizes are not applied. Wins already saved are kept.')
    wheel_every_days = fields.Integer(string='One spin every (days)', default=30,
                                      help='A customer (a signed-in account, or the same phone number) spins once in this many days.')
    wheel_valid_days = fields.Integer(string='Prize valid for (days)', default=14,
                                      help='A prize code works this many days after the spin, unless the prize says otherwise.')
    wheel_tab = fields.Char(string='Side tab', help='The tab on the left edge of every page, e.g. Spin & Win')
    wheel_eyebrow = fields.Char(string='Small line above the title', help='e.g. ✦ [Website name] rewards ✦')
    wheel_title = fields.Char(string='Wheel title', help='e.g. Spin &')
    wheel_title2 = fields.Char(string='Title (gold part)', help='e.g. Win')
    wheel_subtitle = fields.Char(string='Wheel line under the title', help='e.g. Every slice is a free extra on your next repair.')
    wheel_spin = fields.Char(string='Spin button', help='e.g. Spin the wheel')
    wheel_later = fields.Char(string='Wheel close link', help='e.g. Maybe later')
    wheel_won = fields.Char(string='"You won" line', help='e.g. 🎉 You won')
    wheel_note = fields.Char(string='Note under the code', help='e.g. Show this code when you book. Valid on your next repair.')
    wheel_book = fields.Char(string='Book button', help='e.g. Book now')
    wheel_wa = fields.Char(string='Wheel WhatsApp button', help='e.g. WhatsApp us')
    wheel_wa_msg = fields.Char(string='Wheel WhatsApp message', help='[Website name], [Code] = the prize code.')
    # chat assistant
    bot_name = fields.Char(string='Assistant name', help='e.g. [Website name] Assistant')
    bot_status = fields.Char(string='Line under the name', help='e.g. Automated help · replies instantly')
    bot_greeting = fields.Text(string='First message')
    bot_placeholder = fields.Char(string='Typing box hint', help='e.g. Ask about a repair, area or price…')
    bot_tip = fields.Char(string='Chat button tip', help='e.g. Ask us anything')
    bot_wa_tip = fields.Char(string='WhatsApp button tip', help='e.g. WhatsApp us')
    bot_wa_msg = fields.Char(string='Chat WhatsApp message', help='e.g. Hello [Website name] — I need help with a repair.')
    bot_a_book = fields.Text(string='Answer: book a repair')
    bot_a_dev = fields.Text(string='Answer: device chosen', help='[Device] = the device type.')
    bot_a_iss = fields.Text(string='Answer: problem chosen', help='[Problem], [Device] and [Price line] (the price line).')
    bot_a_area = fields.Text(string='Answer: check my area')
    bot_a_price = fields.Text(string='Answer: prices', help='[Visit fee line] = the visit fee line.')
    bot_a_time = fields.Text(string='Answer: how long', help='[Visit time] = the visit time, [Lab time] = the lab time.')
    bot_a_contact = fields.Text(string='Answer: branches & contact', help='[Branches], [Phone], [Email]')
    bot_a_hours = fields.Text(string='Answer: opening hours', help='[Opening hours] = the opening hours.')
    bot_a_human = fields.Text(string='Answer: talk to a person')
    bot_a_menu = fields.Text(string='Answer: back to the menu')
    bot_a_found = fields.Text(string='Answer: area found', help='[Area] = the area typed.')
    bot_a_fallback = fields.Text(string='Answer: not understood')
    # Book-your-slot slider
    eng_eyebrow = fields.Char(string='Slide small line', help='e.g. Book your slot')
    eng_title2 = fields.Char(string='Generic title (green part)', help='For a device type without a slide of its own, e.g. repair at your door')
    eng_perks = fields.Text(string='Generic perks', help='One per line, for a device type without a slide of its own.')
    eng_from_label = fields.Char(string='Price label', help='e.g. Starting from')
    eng_slide_ms = fields.Integer(string='Slide every (ms)', default=3500)
    eng_idle_s = fields.Integer(string='Opens after idle (seconds)', default=35, help='No mouse, scroll, key or touch for this long opens the slider.')
    eng_still_s = fields.Integer(string='Leaving panel after still (seconds)', default=15, help='Cursor still for this long, or leaving through the top, opens the Leaving panel.')
    eng_wa_msg = fields.Char(string='Form WhatsApp message', help='[Website name], [Slide title] = the slide title, [Their number or email] = the number or email typed.')
    eng_form_pill = fields.Char(string='Form green pill', help='e.g. Book instantly on WhatsApp')
    eng_form_title = fields.Char(string='Form title', help='e.g. Book your slot')
    eng_form_subtitle = fields.Char(string='Form line under the title')
    eng_form_privacy = fields.Char(string='Privacy line', help='e.g. No spam. We only use your number to confirm the booking.')
    eng_form_send = fields.Char(string='Send button', help='e.g. Send on WhatsApp')
    eng_form_all = fields.Char(string='"All services" link', help='e.g. View all services')
    eng_form_all_link = fields.Char(string='"All services" link opens', help='e.g. /services#all')
    eng_form_features = fields.Text(string='Three features', help='One per line, "Title|small line", e.g. Quick Service|In most areas')
    # Leaving panel
    exit_title = fields.Char(string='Panel title', help='e.g. Leaving already? 👋')
    exit_status = fields.Char(string='Panel line under the title', help='e.g. We reply on WhatsApp')
    exit_text = fields.Char(string='Panel text')
    exit_button = fields.Char(string='Panel WhatsApp button', help='e.g. Chat with us on WhatsApp')
    exit_wa_msg = fields.Char(string='Panel WhatsApp message', help='e.g. Hi [Website name], I need help with a repair.')
    exit_tile_msg = fields.Char(string='Tile message', help='[Device] = the device type, e.g. Hi [Website name], I need help with my [Device].')
    exit_link = fields.Char(string='Bottom link opens', help='e.g. /#book-services')
    exit_link_label = fields.Char(string='Bottom link', help='e.g. See all services →')

    item_ids = fields.One2many('fix.site.item', 'site_id', string='Pop-up items')

    def _fix_items(self, kind):
        self.ensure_one()
        return self.item_ids.filtered(lambda i: i.kind == kind and i.active).sorted('sequence')

    def _t(self, field):
        return self[field] or ''

    def _fix_popups(self):
        """The ``popups``, ``wheel``, ``bot`` and ``engage`` groups of ``website_content``."""
        self.ensure_one()
        t = self._t
        return {
            'popups': {
                'ann': {'show': bool(self.ann_show), 'text': t('ann_text'), 'button': t('ann_button'), 'link': t('ann_link'),
                        'speed_s': int(self.ann_speed_s or 0)},
                'welcome': {'type': self.welcome_popup or 'slot', 'delay_ms': int(self.welcome_delay_ms or 0),
                            'flash_delay_ms': int(self.welcome_flash_delay_ms or 0), 'snooze_days': int(self.welcome_snooze_days or 0)},
                'flash': {'badge': t('flash_badge'), 'title': t('flash_title'), 'body': t('flash_body'), 'code': t('flash_code'),
                          'button': t('flash_button'), 'button_link': t('flash_button_link'), 'wa_button': t('flash_wa_button'),
                          'wa_msg': t('flash_wa_msg'), 'later': t('flash_later')},
                'cookie': {'show': bool(self.cookie_show), 'title': t('cookie_title'), 'text': t('cookie_text'),
                           'decline': t('cookie_decline'), 'accept': t('cookie_accept'), 'delay_ms': int(self.cookie_delay_ms or 0)},
            },
            'wheel': {
                'show': bool(self.wheel_show), 'every_days': int(self.wheel_every_days or 0),
                'tab': t('wheel_tab'), 'eyebrow': t('wheel_eyebrow'), 'title': t('wheel_title'), 'title2': t('wheel_title2'),
                'subtitle': t('wheel_subtitle'), 'spin': t('wheel_spin'), 'later': t('wheel_later'), 'won': t('wheel_won'),
                'note': t('wheel_note'), 'book': t('wheel_book'), 'wa': t('wheel_wa'), 'wa_msg': t('wheel_wa_msg'),
                'slices': [i._serialize() for i in self._fix_items('wheel')],
            },
            'bot': {
                'name': t('bot_name'), 'status': t('bot_status'), 'greeting': t('bot_greeting'), 'placeholder': t('bot_placeholder'),
                'tip': t('bot_tip'), 'wa_tip': t('bot_wa_tip'), 'wa_msg': t('bot_wa_msg'),
                'replies': [i._serialize() for i in self._fix_items('reply')],
                'answers': {k: t(f'bot_a_{k}') for k in BOT_ANSWERS},
            },
            'engage': {
                'eyebrow': t('eng_eyebrow'), 'title2_generic': t('eng_title2'), 'perks_generic': _lines(self.eng_perks),
                'from_label': t('eng_from_label'), 'slide_ms': int(self.eng_slide_ms or 0), 'idle_s': int(self.eng_idle_s or 0),
                'still_s': int(self.eng_still_s or 0), 'wa_msg': t('eng_wa_msg'),
                'form': {'pill': t('eng_form_pill'), 'title': t('eng_form_title'), 'subtitle': t('eng_form_subtitle'),
                         'privacy': t('eng_form_privacy'), 'send': t('eng_form_send'), 'all': t('eng_form_all'),
                         'all_link': t('eng_form_all_link'),
                         'features': [{'title': a.strip(), 'small': b.strip()} for a, _, b in (x.partition('|') for x in _lines(self.eng_form_features))]},
                'slides': [i._serialize() for i in self._fix_items('slide')],
                'exit': {'title': t('exit_title'), 'status': t('exit_status'), 'text': t('exit_text'), 'button': t('exit_button'),
                         'wa_msg': t('exit_wa_msg'), 'tile_msg': t('exit_tile_msg'), 'link': t('exit_link'),
                         'link_label': t('exit_link_label'),
                         'tiles': [i._serialize() for i in self._fix_items('tile')]},
            },
        }

    def action_fix_items(self):
        return self._fix_site_action('fix.site.item', 'Pop-up items')


class FixSiteItem(models.Model):
    """One row of a pop-up list. ``kind`` says which list; the other columns mean:

    wheel  name = word on the slice (Diagnosis), name2 = word above it (Free), text = the prize
           in full (Free diagnosis), code = prize code, icon, color = slice colour, color2 = text colour,
           chance = how often it is won (%, 0 = on the wheel but never won), month_limit = at most
           this many wins a month (0 = no limit), valid_days = the prize's own validity (0 = the
           site's), free_visit = the prize makes the visit fee free
    reply  name = the chip (🔧 Book a repair), code = what it does (book, area, price, …)
    slide  category_id = device type, name = title (Mobile), name2 = title green part (Repair),
           text = the pitch, text2 = perks one per line
    tile   category_id = device type, name = label on the tile (empty = the device type's name)
    """
    _name = 'fix.site.item'
    _description = 'Website pop-up item'
    _order = 'kind, sequence, id'

    site_id = fields.Many2one('online.service.site', required=True, ondelete='cascade', string='Website',
                              default=lambda self: self.env['online.service.site'].search([], limit=1))
    kind = fields.Selection(ITEM_KINDS, required=True, default='wheel', string='List')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(string='Shown', default=True)
    name = fields.Char(string='Label', help='Prize: the word on the slice · Reply: the chip · Slide: the title · Tile: the label (empty = the device type).')
    name2 = fields.Char(string='Second label', help='Prize: the small word above (Free / Priority) · Slide: the green part of the title.')
    text = fields.Text(string='Text', help='Prize: the prize in full · Slide: the pitch under the title.')
    text2 = fields.Text(string='Perks', help='Slide: one per line.')
    code = fields.Char(string='Code / action', help='Prize: the code the visitor gets · Reply: what the chip does.')
    icon = fields.Selection(ICONS, string='Icon', help='Prize: the icon on the slice.')
    color = fields.Char(string='Colour', help='Prize: the slice colour, e.g. #f5b400 or var(--violet).')
    color2 = fields.Char(string='Text colour', help='Prize: the text colour on the slice, e.g. #fff.')
    link = fields.Char(string='Opens')
    category_id = fields.Many2one('device.category', string='Device type', ondelete='set null', help='Slide / tile: the device type it is for.')
    # Spin & Win: how the prize is handed out (Odoo picks the prize; the browser only draws the spin)
    chance = fields.Integer(string='Chance (%)', default=0,
                            help='Prize: how often it is won, against the other prizes. 0 = on the wheel, never won.')
    month_limit = fields.Integer(string='At most a month', default=0, help='Prize: no more wins than this in a calendar month. 0 = no limit.')
    valid_days = fields.Integer(string='Valid for (days)', default=0, help='Prize: its own validity. 0 = the website\'s "Prize valid for".')
    free_visit = fields.Boolean(string='Makes the visit free', default=False,
                                help='Prize: the job card\'s inspection becomes free (no visit fee), e.g. "Free diagnosis".')

    def _serialize(self):
        self.ensure_one()
        if self.kind == 'wheel':
            # the odds stay here: the site only needs the id to land the wheel on the prize Odoo chose
            return {'id': self.id, 'top': self.name2 or '', 'label': self.name or '', 'full': self.text or '', 'code': self.code or '',
                    'icon': self.icon or '', 'color': self.color or '', 'text_color': self.color2 or ''}
        if self.kind == 'reply':
            return {'label': self.name or '', 'intent': self.code or ''}
        cat = {'category_id': self.category_id.id or 0, 'category': self.category_id.name or ''}
        if self.kind == 'slide':
            return dict(cat, title=self.name or '', title2=self.name2 or '', pitch=self.text or '', perks=_lines(self.text2))
        return dict(cat, label=self.name or '')
