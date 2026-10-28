# -*- coding: utf-8 -*-
"""The tool bag (visits/models/visit_tools.py): leaving the office once a day before Start trip,
"Before you leave" before the technician's own closing step, a missing tool tracked until found."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_visit import HOST, DoorstepCase
from .test_visit_checks import PNG, b64


@tagged('post_install', '-at_install')
class TestVisitTools(DoorstepCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.heat_gun, cls.tweezers = cls.env['fix.tool.item'].create(
            [{'name': 'Heat gun', 'sequence': 1}, {'name': 'Tweezers', 'sequence': 2}])
        cls.manager = new_test_user(cls.env, login='fs_tool_manager',
                                    groups='base.group_user,mobile_repair.group_mobile_repair_manager')

    def _assigned(self, phone='+968 9123 4567'):
        order, visit = self._visit(phone=phone)
        visit.action_assign()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        token = dict(part.split('=', 1) for part in link.split('&'))['t']
        return order, visit, token

    def _page(self, visit, token, action='', **kw):
        return self.env['fix.service.visit'].tech_page(HOST, visit.name, token, action=action, **kw)

    def _fill(self, visit, token, missing=()):
        """Mark every tool (in the bag, or missing with a note), the bag photo, done. While working,
        "Can it be fixed?" is answered first (that opens "Before you leave")."""
        if visit.state == 'in_progress' and not visit.check_outcome:
            visit.check_outcome = 'parts'
        for line in self._page(visit, token)['tools']['lines']:
            gone = line['name'] in missing
            self._page(visit, token, 'tool_mark', line_id=line['id'], mark='missing' if gone else 'ok',
                       note='left in the car' if gone else None)
        self.assertTrue(self._page(visit, token, 'tool_photo', data=b64(PNG))['ok'])
        done = self._page(visit, token, 'tool_done')
        self.assertTrue(done['ok'], done)
        return done

    def _working(self, visit, token):
        """Leaving the office done, on the way, arrived and working (the safety check skipped)."""
        if self._page(visit, token).get('tools'):
            self._fill(visit, token)
        self.assertEqual(self._page(visit, token, 'on_the_way')['state'], 'on_the_way')
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        visit.with_context(fix_checks_passed=True).action_start()
        self.assertEqual(visit.state, 'in_progress')

    # ------------------------------------------------------------------ leaving the office
    def test_office_check_once_a_day(self):
        _order, visit, token = self._assigned()
        page = self._page(visit, token)
        tools = page['tools']
        self.assertEqual(tools['kind'], 'office')
        self.assertTrue(tools['required'])
        self.assertEqual([l['name'] for l in tools['lines']], ['Heat gun', 'Tweezers'])

        refused = self._page(visit, token, 'on_the_way')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error'], 'tools')
        self.assertEqual(visit.state, 'assigned')
        early = self._page(visit, token, 'tool_done')
        self.assertFalse(early['ok'])
        self.assertIn('Bag photo', early['message'])

        for line in tools['lines']:
            marked = self._page(visit, token, 'tool_mark', line_id=line['id'], mark='ok')
        self.assertEqual({l['state'] for l in marked['tools']['lines']}, {'ok'})
        self.assertEqual(marked['tools']['missing'], ['Bag photo'])     # every tool marked: only the photo left
        self.assertTrue(self._page(visit, token, 'tool_photo', data=b64(PNG))['ok'])
        self.assertTrue(self._page(visit, token, 'tool_done')['ok'])
        self.assertNotIn('tools', self._page(visit, token))
        self.assertEqual(self._page(visit, token, 'on_the_way')['state'], 'on_the_way')

        # the second trip of the day: no office check again
        _order2, second, token2 = self._assigned(phone='+968 9123 7777')
        self.assertNotIn('tools', self._page(second, token2))
        self.assertEqual(self._page(second, token2, 'on_the_way')['state'], 'on_the_way')

    def test_photo_must_be_a_photo(self):
        _order, visit, token = self._assigned()
        bad = self._page(visit, token, 'tool_photo', data=b64(b'not a picture at all'))
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['error'], 'tools')

    # ------------------------------------------------------------------ leaving the house
    def test_house_check_before_closing(self):
        _order, visit, token = self._assigned()
        self._working(visit, token)
        self.assertTrue(visit.tool_house_due)
        self.assertNotIn('tools', self._page(visit, token))     # not before "Can it be fixed?"
        visit.check_outcome = 'parts'
        tools = self._page(visit, token)['tools']
        self.assertEqual(tools['kind'], 'house')
        self.assertEqual(tools['title'], 'Before you leave')
        self.assertFalse(tools['for_ref'])

        refused = self._page(visit, token, 'done')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error'], 'tools')
        self.assertEqual(visit.state, 'in_progress')
        fixed = self._page(visit, token, 'result_fixed')        # Fixed on the spot waits too
        self.assertEqual(fixed['error'], 'tools')
        self.assertFalse(visit.close_stage)

        self._fill(visit, token)
        self.assertFalse(visit.tool_house_due)
        self.assertEqual(self._page(visit, token, 'done')['state'], 'done')

    def test_closing_steps(self):
        _order, visit, token = self._assigned()
        self._working(visit, token)
        self.assertTrue(visit._vt_closing('close_code', {}))
        self.assertTrue(visit._vt_closing('result_later', {}))
        self.assertTrue(visit._vt_closing('result_outcome', {'outcome': 'not_worth'}))
        # no fault with the visit fee: Finish (payment, code) comes first, that one asks
        self.assertFalse(visit._vt_closing('result_outcome', {'outcome': 'no_fault', 'fee': True}))
        self.assertFalse(visit._vt_closing('result_outcome', {'outcome': 'parts'}))
        self.assertTrue(visit._vt_closing('result_fixed', {}))       # tools back before Finish
        self.assertFalse(visit._vt_closing('result_note', {}))

    def test_needs_parts_is_not_fixed_on_the_spot_without_a_part(self):
        _order, visit, token = self._assigned()
        self._working(visit, token)
        visit.check_outcome = 'parts'
        with self.assertRaises(UserError):
            visit._vr_fixed()                   # no part added yet
        self.assertFalse(visit.close_stage)

    def test_house_left_unchecked_asks_before_the_next_trip(self):
        _order, visit, token = self._assigned()
        self._working(visit, token)
        visit.action_done()                     # closed by the office: the bag was not checked
        self.assertTrue(visit.tool_house_due)
        self.assertTrue(self._page(visit, token)['tools'])      # its own page still asks

        _order2, second, token2 = self._assigned(phone='+968 9123 7777')
        tools = self._page(second, token2)['tools']
        self.assertEqual(tools['kind'], 'house')
        self.assertEqual(tools['for_ref'], visit.name)
        self.assertFalse(self._page(second, token2, 'on_the_way')['ok'])
        self._fill(second, token2)              # done from the next visit's page
        self.assertFalse(visit.tool_house_due)
        self.assertNotIn('tools', self._page(second, token2))   # leaving the office was done today
        self.assertEqual(self._page(second, token2, 'on_the_way')['state'], 'on_the_way')

    # ------------------------------------------------------------------ missing tools
    def test_missing_tool_never_blocks_and_is_tracked(self):
        order, visit, token = self._assigned()
        self._fill(visit, token, missing=('Heat gun',))
        self.assertEqual(self._page(visit, token, 'on_the_way')['state'], 'on_the_way')
        Line = self.env['fix.tool.check.line']
        open_lines = Line.search([('technician_id', '=', self.employee.id), ('is_open', '=', True)])
        self.assertEqual(open_lines.tool_id, self.heat_gun)
        self.assertEqual(open_lines.where, 'Leaving the office')
        self.assertEqual(open_lines.note, 'left in the car')
        self.assertEqual(open_lines.check_id.missing_text, 'Heat gun')
        self.assertEqual(order._fix_desk_row()['tools_missing'], 'Heat gun')
        self.assertEqual([t['name'] for t in self._page(visit, token)['tools_missing']], ['Heat gun'])
        # the red chip is only on the booking where it went missing; the technician's page warns everywhere
        order2, second, token2 = self._assigned(phone='+968 9123 7777')
        self.assertEqual(order2._fix_desk_row()['tools_missing'], '')
        self.assertEqual([t['name'] for t in self._page(second, token2)['tools_missing']], ['Heat gun'])

        # still missing when leaving the house: kept on the first check (where it went missing)
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        visit.with_context(fix_checks_passed=True).action_start()
        self._fill(visit, token, missing=('Heat gun',))
        self.assertEqual(Line.search([('technician_id', '=', self.employee.id), ('is_open', '=', True)]), open_lines)
        self.assertTrue(visit.tool_house_check_id.line_ids.filtered(lambda l: l.tool_id == self.heat_gun).known)

        open_lines.action_found()
        self.assertFalse(open_lines.is_open)
        self.assertTrue(open_lines.found_by_id)
        self.assertFalse(self._page(visit, token)['tools_missing'])
        self.assertFalse(order._fix_desk_row()['tools_missing'])

    def test_back_in_the_bag_closes_the_missing(self):
        _order, visit, token = self._assigned()
        self._fill(visit, token, missing=('Tweezers',))
        self._page(visit, token, 'on_the_way')
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        visit.with_context(fix_checks_passed=True).action_start()
        lost = self.env['fix.tool.check.line'].search([('technician_id', '=', self.employee.id), ('is_open', '=', True)])
        self.assertEqual(lost.tool_id, self.tweezers)
        self._fill(visit, token)               # everything in the bag when leaving the house
        self.assertTrue(lost.found)
        self.assertFalse(lost.is_open)
        self.assertIn('In the bag again', lost.found_note)

    # ------------------------------------------------------------------ the office
    def test_desk_shows_office_and_service_place(self):
        order, visit, token = self._assigned()
        bag = order.fix_desk_detail()['visit']['tools']
        self.assertFalse(bag['start'])                          # not asked yet
        self.assertFalse(bag['house'])
        self._fill(visit, token, missing=('Tweezers',))
        self._page(visit, token, 'on_the_way')
        bag = order.fix_desk_detail()['visit']['tools']
        self.assertEqual((bag['start']['kind'], bag['start']['state']), ('office', 'done'))
        self.assertEqual(bag['start']['missing'], 1)
        self.assertTrue(bag['start']['photo'])
        self.assertEqual({t['name']: t['state'] for t in bag['start']['tools']}, {'Heat gun': 'ok', 'Tweezers': 'missing'})
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        visit.with_context(fix_checks_passed=True).action_start()
        self._fill(visit, token)
        bag = order.fix_desk_detail()['visit']['tools']
        self.assertEqual((bag['house']['state'], bag['house']['missing']), ('done', 0))
        self.assertEqual(bag['start']['kind'], 'office')        # its own place is not "the last place"
        self._page(visit, token, 'done')

        # the 2nd visit of the day set off with the bag checked at the 1st customer's place
        order2, second, token2 = self._assigned(phone='+968 9123 7777')
        self.assertEqual(self._page(second, token2, 'on_the_way')['state'], 'on_the_way')
        start = order2.fix_desk_detail()['visit']['tools']['start']
        self.assertEqual((start['kind'], start['ref']), ('house', visit.name))
        self.assertEqual(start['customer'], visit.customer_name)
        self.assertEqual(order.fix_desk_detail()['visit']['tools']['start']['kind'], 'office')   # visit 1 unchanged

    def test_manager_skips_a_check(self):
        _order, visit, token = self._assigned()
        self._page(visit, token)
        check = visit._vt_office_check(create=False)
        self.assertEqual(check.state, 'todo')
        with self.assertRaises(AccessError):
            check.with_user(self.tech_user).action_skip()
        with self.assertRaises(UserError):
            check.with_user(self.manager).action_skip()        # no reason
        check.skip_reason = 'Bag checked by phone'
        check.with_user(self.manager).action_skip()
        self.assertEqual(check.state, 'skipped')
        self.assertEqual(check.skipped_by_id, self.manager)
        self.assertEqual(self._page(visit, token, 'on_the_way')['state'], 'on_the_way')

    def test_empty_list_asks_nothing(self):
        (self.heat_gun | self.tweezers).active = False
        _order, visit, token = self._assigned()
        self.assertNotIn('tools', self._page(visit, token))
        self.assertEqual(self._page(visit, token, 'on_the_way')['state'], 'on_the_way')
        self.assertTrue(visit._fs_arrive(skip_code=True)['ok'])
        visit.with_context(fix_checks_passed=True).action_start()
        self.assertFalse(visit.tool_house_due)

    def test_my_visits_asks_too(self):
        _order, visit, _token = self._assigned()
        mine = visit.with_user(self.tech_user)
        view = mine.fix_tech_view()
        self.assertEqual(view['tools']['kind'], 'office')
        refused = mine.fix_tech_act('on_the_way')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error'], 'tools')
        for line in view['tools']['lines']:
            mine.fix_tech_act('tool_mark', line_id=line['id'], mark='ok')
        mine.fix_tech_act('tool_photo', data=b64(PNG))
        self.assertTrue(mine.fix_tech_act('tool_done')['ok'])
        self.assertEqual(mine.fix_tech_act('on_the_way')['state'], 'on_the_way')
