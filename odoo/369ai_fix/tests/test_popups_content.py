# -*- coding: utf-8 -*-
"""Pop-ups & chat (website/models/site_popups.py): the starter texts fill once and keep
edits, website_content hands the four groups to the site, an edit or a hidden prize changes
the output, the editor load carries the items, and placeholders travel raw."""
import importlib

from odoo.tests import TransactionCase, new_test_user, tagged

seed = importlib.import_module('odoo.addons.369ai_fix.website.seed')   # the add-on's name starts with a digit

HOST = 'popups-test.example'
STARTER = seed.starter_content()['popups']


@tagged('post_install', '-at_install')
class TestPopupsContent(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['online.service.site'].create({'name': 'Pop-ups Test', 'domains': HOST, 'opening_hours': 'Sat–Thu 9:00–21:00'})
        cls.Order = cls.env['online.service.order']
        cls.editor = new_test_user(cls.env, login='popups_editor', groups='base.group_user,369ai_fix.group_fix_website_editor')
        seed._fill_popups(cls.site, {'popups': STARTER})

    def _content(self):
        data = self.Order.website_content(HOST)
        self.assertTrue(data['ok'], data)
        return data['site']

    def _items(self, kind):
        return self.site.item_ids.filtered(lambda i: i.kind == kind)

    def test_seed_fills_once_and_keeps_edits(self):
        site = self.site
        self.assertEqual(site.flash_code, '369FIX')
        self.assertEqual(site.ann_text, STARTER['fields']['ann_text'])
        self.assertEqual(site.welcome_popup, 'slot')
        self.assertEqual(site.eng_idle_s, 35)
        self.assertEqual(len(self._items('wheel')), 6)
        self.assertEqual(len(self._items('reply')), 6)
        self.assertEqual(len(self._items('tile')), 6)
        # slides and tiles name a device type; every starter one exists in the catalogue
        self.assertEqual(len(self._items('slide')), 5)
        self.assertTrue(all(i.category_id for i in self._items('slide') | self._items('tile')))
        # a second run keeps an edit and adds nothing
        site.write({'flash_code': 'EDITED', 'wheel_title': False})
        self._items('wheel')[0].unlink()
        seed._fill_popups(site, {'popups': STARTER})
        self.assertEqual(site.flash_code, 'EDITED')
        self.assertEqual(site.wheel_title, 'Spin &', 'an emptied field is filled again')
        self.assertEqual(len(self._items('wheel')), 5, 'a list that has rows is left alone')

    def test_website_content_has_the_four_groups(self):
        c = self._content()
        self.assertEqual(c['popups']['ann'], {'show': True, 'text': STARTER['fields']['ann_text'], 'button': 'Book now →',
                                              'link': '/services#catalog', 'speed_s': 30})
        self.assertEqual(c['popups']['welcome'], {'type': 'slot', 'delay_ms': 1500, 'flash_delay_ms': 4000, 'snooze_days': 30})
        self.assertEqual(c['popups']['flash']['code'], '369FIX')
        self.assertEqual(c['popups']['cookie']['delay_ms'], 1200)
        self.assertIsInstance(c['popups']['cookie']['show'], bool)
        wheel = c['wheel']
        self.assertEqual(len(wheel['slices']), 6)
        first = dict(wheel['slices'][0])
        self.assertEqual(first.pop('id'), self._items('wheel').sorted('sequence')[0].id, 'the wheel lands on the prize by its id')
        self.assertEqual(first, {'top': 'Free', 'label': 'Diagnosis', 'full': 'Free diagnosis', 'code': 'SPIN-DIAG',
                                 'icon': 'diag', 'color': 'var(--violet)', 'text_color': '#fff'})
        self.assertTrue(wheel['show'])
        self.assertEqual(wheel['every_days'], 30)
        # the starter chances: most spins win something small, the priority slot is show only
        by_code = {i.code: i for i in self._items('wheel')}
        self.assertEqual((by_code['SPIN-CLEAN'].chance, by_code['SPIN-FAST'].chance), (35, 0))
        self.assertTrue(by_code['SPIN-DIAG'].free_visit)
        self.assertEqual(wheel['slices'][4]['color'], 'color-mix(in srgb, var(--violet) 55%, #fff)')
        bot = c['bot']
        self.assertEqual([r['intent'] for r in bot['replies']], ['book', 'area', 'price', 'time', 'contact', 'human'])
        self.assertEqual(bot['replies'][0]['label'], '🔧 Book a repair')
        self.assertEqual(set(bot['answers']), {'book', 'dev', 'iss', 'area', 'price', 'time', 'contact', 'hours', 'human', 'menu', 'found', 'fallback'})
        self.assertEqual(bot['answers']['hours'], "We're open {hours}.")
        eng = c['engage']
        self.assertEqual(eng['perks_generic'], ['Expert technicians', 'Price confirmed first', 'At your door', 'Updates on WhatsApp'])
        self.assertEqual(eng['form']['features'][0], {'title': 'Quick Service', 'small': 'In most areas'})
        self.assertEqual((eng['slide_ms'], eng['idle_s'], eng['still_s']), (3500, 35, 15))
        mobile = self.env['device.category'].search([('name', '=ilike', 'Mobile Phone')], limit=1)
        self.assertEqual(eng['slides'][0], {'category_id': mobile.id, 'category': mobile.name, 'title': 'Mobile', 'title2': 'Repair',
                                            'pitch': 'Screen, battery, charging, camera and more – quick and reliable service.',
                                            'perks': ['Genuine parts', 'Expert technicians', 'Affordable pricing', 'Quick turnaround']})
        self.assertEqual(len(eng['exit']['tiles']), 6)
        self.assertEqual(eng['exit']['tiles'][0], {'category_id': mobile.id, 'category': mobile.name, 'label': 'Mobile Phone'})
        self.assertEqual(eng['exit']['link'], '/#book-services')

    def test_placeholders_travel_raw_and_empty_is_blank(self):
        c = self._content()
        self.assertEqual(c['wheel']['eyebrow'], '✦ {site} rewards ✦')
        self.assertEqual(c['bot']['name'], '{site} Assistant')
        self.assertIn('{fee}', c['popups']['flash']['body'])
        self.assertIn('{code}', c['popups']['flash']['wa_msg'])
        self.site.write({'wheel_title': False, 'bot_a_menu': False, 'eng_perks': False})
        c = self._content()
        self.assertEqual(c['wheel']['title'], '')
        self.assertEqual(c['bot']['answers']['menu'], '')
        self.assertEqual(c['engage']['perks_generic'], [])

    def test_an_edit_and_a_hidden_prize_change_the_output(self):
        self.site.write({'ann_text': 'Closed on Friday', 'ann_show': False, 'welcome_popup': 'spin', 'ann_speed_s': 45})
        self._items('wheel').filtered(lambda i: i.code == 'SPIN-PICK').write({'active': False})
        self._items('reply')[0].write({'sequence': 99})
        c = self._content()
        self.assertEqual(c['popups']['ann']['text'], 'Closed on Friday')
        self.assertFalse(c['popups']['ann']['show'])
        self.assertEqual(c['popups']['ann']['speed_s'], 45)
        self.assertEqual(c['popups']['welcome']['type'], 'spin')
        self.assertEqual([s['code'] for s in c['wheel']['slices']], ['SPIN-DIAG', 'SPIN-CLEAN', 'SPIN-FAST', 'SPIN-DATA', 'SPIN-GUARD'])
        self.assertEqual(c['bot']['replies'][-1]['intent'], 'book', 'lists follow the sequence')

    def test_editor_load_carries_the_items(self):
        Site = self.env['online.service.site'].with_user(self.editor)
        d = Site.fix_editor_load(site_id=self.site.id)
        self.assertEqual(d['site_id'], self.site.id)
        self.assertEqual({i['kind'] for i in d['items']}, {'wheel', 'reply', 'slide', 'tile'})
        wheel = [i for i in d['items'] if i['kind'] == 'wheel']
        self.assertEqual(wheel[0]['name2'], 'Free')
        self.assertEqual(wheel[0]['color'], 'var(--violet)')
        self.assertEqual(wheel[0]['category_id'], False)
        slide = [i for i in d['items'] if i['kind'] == 'slide'][0]
        self.assertIsInstance(slide['category_id'], int)
        self.assertEqual(d['site']['flash_code'], '369FIX')
        self.assertEqual(d['site']['welcome_popup'], 'slot')
        self.assertEqual(d['site']['eng_idle_s'], 35)
        self.assertEqual(d['hours'], 'Sat–Thu 9:00–21:00')
        # an editor may add a prize from the screen and the site sends it
        self.env['fix.site.item'].with_user(self.editor).create({
            'site_id': self.site.id, 'kind': 'wheel', 'name': 'Cable', 'name2': 'Free', 'text': 'Free cable', 'code': 'SPIN-CABLE', 'sequence': 70})
        self.assertEqual(self._content()['wheel']['slices'][-1]['full'], 'Free cable')
