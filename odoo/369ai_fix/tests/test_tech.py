# -*- coding: utf-8 -*-
"""My Visits (app/models/fix_tech.py): the technician's own screen in Odoo runs the web page's
steps with their login; only their own visits, and no flag can skip the safety check."""
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .test_visit import DoorstepCase
from .test_visit_checks import MP4, PNG, b64


@tagged('post_install', '-at_install')
class TestMyVisits(DoorstepCase):

    def _assigned(self):
        order, visit = self._visit()
        visit.action_assign()
        return order, visit

    def test_my_visits_walk_through(self):
        _order, visit = self._assigned()
        mine = visit.with_user(self.tech_user)
        Visit = self.env['fix.service.visit'].with_user(self.tech_user)
        load = Visit.fix_tech_load()
        self.assertTrue(load['linked'])
        self.assertIn(visit.id, [v['id'] for v in load['visits']])

        self.assertEqual(mine.fix_tech_view()['state'], 'assigned')
        self.assertEqual(mine.fix_tech_act('on_the_way', lat=23.59, lng=58.40, accuracy=12)['state'], 'on_the_way')
        self.assertTrue(visit.tech_fix_on)                                  # the location was kept
        wrong = mine.fix_tech_act('arrive', code='0000' if visit.arrival_code != '0000' else '1111')
        self.assertFalse(wrong['ok'])
        page = mine.fix_tech_act('arrive', code=visit.arrival_code)
        self.assertEqual(page['state'], 'arrived')
        self.assertIn('checks', page)

        # Start work waits for the checks - even with a "checks passed" flag in the context
        refused = mine.with_context(fix_checks_passed=True).fix_tech_act('start')
        self.assertFalse(refused['ok'])
        self.assertEqual(visit.state, 'arrived')

        checks = page['checks']
        for item in checks['safety']:
            mine.fix_tech_act('check_tick', item_id=item['id'], done=True)
        self.assertTrue(mine.fix_tech_act('check_safety_photo', data=b64(PNG))['ok'])
        for side in checks['sides']:
            mine.fix_tech_act('check_side_photo', photo_id=side['id'], data=b64(PNG))
        self.assertFalse(mine.fix_tech_view()['video'])                     # no video yet: no player
        self.assertTrue(mine.fix_tech_act('check_video', name='device.mp4', data=b64(MP4))['ok'])
        video = mine.fix_tech_view()['video']                                # played in My Visits
        self.assertIn('/web/content/fix.service.visit/%d/device_video' % visit.id, video['url'])
        self.assertTrue(visit.with_user(self.tech_user).device_video)       # the technician may read it
        page = mine.fix_tech_act('start')
        self.assertTrue(page['ok'], page)
        self.assertEqual(visit.state, 'in_progress')
        self.assertEqual(page['result']['stage'], 'find')                    # What did you find? next
        self.assertIn('My Visits', ' '.join(visit.message_ids.mapped('body')))

    def test_search_my_visits(self):
        """My Visits' search: the technician's own visits of any date, by visit or booking number."""
        order, visit = self._assigned()
        Visit = self.env['fix.service.visit'].with_user(self.tech_user)
        for words in (visit.name, visit.name.split('/')[-1], order.name):
            found = Visit.fix_tech_search(words)
            self.assertIn(visit.id, [r['id'] for r in found['rows']], words)
            self.assertGreaterEqual(found['count'], 1)
        self.assertEqual(Visit.fix_tech_search('x'), {'count': 0, 'rows': []})
        # another technician's visit is not found
        other = new_test_user(self.env, login='tech_other_search', groups='base.group_user,mobile_repair.group_mobile_repair_technician')
        self.env['hr.employee'].create({'name': 'Other Tech', 'user_id': other.id})
        self.assertNotIn(visit.id, [r['id'] for r in
                                    self.env['fix.service.visit'].with_user(other).fix_tech_search(visit.name)['rows']])

    def test_only_my_own_visits(self):
        _order, visit = self._assigned()
        stranger = visit.with_user(self.other_user)
        with self.assertRaises(AccessError):
            stranger.fix_tech_view()
        with self.assertRaises(AccessError):
            stranger.fix_tech_act('on_the_way')
        self.assertEqual(visit.state, 'assigned')
        load = self.env['fix.service.visit'].with_user(self.other_user).fix_tech_load()
        self.assertFalse(load['linked'])
        self.assertEqual(load['visits'], [])

    def test_the_web_page_still_works(self):
        _order, visit = self._assigned()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        token = dict(part.split('=', 1) for part in link.split('&'))['t']
        from .test_visit import HOST
        page = self.env['fix.service.visit'].tech_page(HOST, visit.name, token, action='on_the_way')
        self.assertEqual(page['state'], 'on_the_way')
        self.assertEqual(visit.with_user(self.tech_user).fix_tech_view()['state'], 'on_the_way')
