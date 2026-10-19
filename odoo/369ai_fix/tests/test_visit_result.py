# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_visit import HOST, DoorstepCase


@tagged('post_install', '-at_install')
class TestVisitResult(DoorstepCase):
    """What the technician found, and the quotation first (as on Urban Company)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['device.category'].create({'name': 'VR Phones'})
        cls.brand = cls.env['device.brand'].create({'name': 'VR Brand', 'category_id': cls.category.id})
        Product = cls.env['product.product']
        cls.in_office = Product.create({'name': 'VR Screen', 'type': 'consu', 'is_storable': True,
                                        'sale_ok': True, 'lst_price': 20.0})
        cls.to_order = Product.create({'name': 'VR Back glass', 'type': 'consu', 'is_storable': True,
                                       'sale_ok': True, 'lst_price': 12.0})
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.in_office, warehouse.lot_stock_id, 5)

    def _working(self):
        order, visit = self._visit()
        visit.action_assign()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        token = dict(part.split('=', 1) for part in link.split('&'))['t']
        visit.action_on_the_way()
        visit._fs_arrive(skip_code=True)
        visit.with_context(fix_checks_passed=True).action_start()
        self.assertEqual(visit.state, 'in_progress')
        return order, visit, token

    def _wizard(self, visit, products=(), **vals):
        return self.env['fix.visit.result.wizard'].with_context(default_visit_id=visit.id).create(dict({
            'brand_id': self.brand.id, 'category_id': self.category.id,
            'line_ids': [(0, 0, {'product_id': p.id, 'qty': 1}) for p in products],
        }, **vals))

    def _quote(self, visit, products, **vals):
        before = len(self.sent)
        self._wizard(visit, products, **vals).action_quote()
        self.assertEqual(visit.check_result, 'waiting')
        self.assertEqual(visit.state, 'in_progress')               # the technician waits for the OK
        self.assertEqual(visit.job_card_id.quote_state, 'waiting')
        texts = [t for _p, t in self.sent[before:]]
        self.assertTrue(any('/quote?' in t for t in texts), texts)
        return texts

    def _receive_parts(self, card):
        requests = self.env['spare.part.purchase.request'].search([('job_card_id', '=', card.id)])
        self.assertTrue(requests)
        requests.write({'state': 'ordered', 'expected_date': fields.Date.context_today(card)})
        requests.write({'state': 'received'})

    # ------------------------------------------------------------------ no part
    def test_fixed_on_the_spot_without_parts(self):
        _order, visit, _token = self._working()
        before = len(self.sent)
        self._wizard(visit, found='Loose cable, fixed').action_fixed()
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'fixed')
        self.assertFalse([t for _p, t in self.sent[before:] if '/quote?' in t])   # no quotation

    def test_parts_need_the_quotation_first(self):
        _order, visit, _token = self._working()
        wiz = self._wizard(visit, [self.in_office])
        with self.assertRaises(UserError):
            wiz.action_fixed()
        self.assertEqual(visit.state, 'in_progress')

    def test_needs_a_brand_without_job_card(self):
        _order, visit, _token = self._working()
        with self.assertRaises(UserError):
            visit._vr_card()
        card = visit._vr_card(brand=self.brand)
        self.assertEqual(card.state, 'inspection')
        self.assertEqual(visit._vr_card(), card)

    # ------------------------------------------------------------------ part in the office
    def test_in_office_fix_now_approved_at_the_door(self):
        _order, visit, _token = self._working()
        texts = self._quote(visit, [self.in_office], plan_here='now')
        self.assertTrue(any('fixes it now' in t for t in texts), texts)
        visit._vr_approved_here()
        self.assertEqual(visit.check_result, 'repairing')
        self.assertEqual(visit.job_card_id.quote_state, 'accepted')
        visit._vr_fixed()
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'fixed')

    def test_in_office_take_approved_by_link(self):
        order, visit, _token = self._working()
        texts = self._quote(visit, [self.in_office], plan_here='take', days=1, days_unit='weeks')
        back_by = fields.Date.add(fields.Date.context_today(visit), days=7)
        self.assertTrue(any('within 1 week' in t and back_by.strftime('%a %d %b') in t for t in texts), texts)
        self.assertFalse(visit.job_card_id.wb_at_office)            # nothing taken before the OK
        visit.job_card_id._wb_quote_approved()                      # what the /quote page does
        self.assertEqual(visit.check_result, 'to_take')
        before = len(self.sent)
        visit._vr_take(no_accessories=True)
        card = visit.job_card_id
        self.assertTrue(card.wb_at_office)
        self.assertEqual(card.wb_return_by, back_by)
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'office')
        texts = [t for _p, t in self.sent[before:]]
        self.assertEqual(len(texts), 1, texts)
        self.assertIn('with us', texts[0])

    def test_in_office_come_back(self):
        order, visit, _token = self._working()
        self._quote(visit, [self.in_office], plan_here='come_back', days=3)
        visit._vr_approved_here()
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'come_back')
        self.assertEqual(order.parts_state, 'ready')
        self.assertIn('within 3 days', self.sent[-1][1])
        self.assertIn('/slot?', self.sent[-1][1])

    # ------------------------------------------------------------------ part to order
    def test_to_order_customer_keeps_it(self):
        order, visit, _token = self._working()
        Request = self.env['spare.part.purchase.request']
        texts = self._quote(visit, [self.to_order], plan_order='keep', part_days=4)
        self.assertTrue(any('about 4 days' in t for t in texts), texts)
        card = visit.job_card_id
        self.assertFalse(Request.search([('job_card_id', '=', card.id)]))          # nothing ordered yet
        card._wb_quote_approved()
        self.assertTrue(Request.search([('job_card_id', '=', card.id)]))           # ordered after the OK
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'ordered')
        self._receive_parts(card)
        self.assertIn('/slot?', self.sent[-1][1])                                # pick a time

    def test_to_order_take_to_office(self):
        order, visit, _token = self._working()
        self._quote(visit, [self.to_order], plan_order='order_take', part_days=5, days=2)
        visit._vr_approved_here()
        self.assertEqual(visit.check_result, 'to_take')
        visit._vr_take(no_accessories=True)
        card = visit.job_card_id
        back_by = fields.Date.add(fields.Date.context_today(visit), days=7)
        self.assertEqual(card.wb_return_by, back_by)
        self.assertIn('about 5 days', self.sent[-1][1])
        self.assertIn(back_by.strftime('%a %d %b'), self.sent[-1][1])
        self._receive_parts(card)
        self.assertIn("We're repairing your device", self.sent[-1][1])
        self.assertNotIn('/slot?', self.sent[-1][1])

    def test_quote_needs_the_part_days(self):
        _order, visit, _token = self._working()
        with self.assertRaises(UserError):
            self._wizard(visit, [self.to_order], part_days=0).action_quote()

    # ------------------------------------------------------------------ declined / later
    def test_declined_nothing_done(self):
        order, visit, _token = self._working()
        self._quote(visit, [self.to_order], plan_order='keep', part_days=4)
        visit._vr_declined_here()
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'declined')
        self.assertEqual(visit.job_card_id.quote_state, 'declined')
        self.assertFalse(self.env['spare.part.purchase.request'].search([('job_card_id', '=', visit.job_card_id.id)]))

    def test_decide_later_then_approve(self):
        order, visit, _token = self._working()
        self._quote(visit, [self.in_office], plan_here='now')
        visit._vr_decide_later()
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'quoted')
        visit.job_card_id._wb_quote_approved()            # later, on the link: we come back
        self.assertEqual(visit.check_result, 'come_back')
        self.assertIn('/slot?', self.sent[-1][1])

    def test_decide_later_then_decline_by_link(self):
        order, visit, token = self._working()
        self._quote(visit, [self.in_office], plan_here='now')
        visit._vr_decide_later()
        link = [t for _p, t in self.sent if '/quote?' in t][-1].split('/quote?', 1)[1].split()[0]
        params = dict(part.split('=', 1) for part in link.split('&'))
        result = order.quote_answer(HOST, params['o'], params['t'], False)
        self.assertTrue(result['ok'])
        self.assertEqual(visit.check_result, 'declined')

    # ------------------------------------------------------------------ the phone
    def test_technician_page(self):
        _order, visit, token = self._working()
        Visit = self.env['fix.service.visit']
        page = Visit.tech_page(HOST, visit.name, token)
        self.assertEqual(page['result']['stage'], 'find')
        self.assertTrue(page['result']['need_device'])
        found = Visit.tech_page(HOST, visit.name, token, action='result_parts', query='VR Screen')
        self.assertEqual(found['parts'][0]['product_id'], self.in_office.id)
        self.assertEqual(found['parts'][0]['status'], 'in_stock')
        page = Visit.tech_page(HOST, visit.name, token, action='result_add_part',
                               product_id=self.in_office.id, brand_id=self.brand.id)
        self.assertEqual(len(page['result']['lines']), 1)
        self.assertTrue(page['result']['needs_quote'])
        self.assertEqual(Visit.tech_page(HOST, visit.name, token, action='result_fixed')['error'], 'result')
        page = Visit.tech_page(HOST, visit.name, token, action='result_quote', plan='take', days=2, unit='days',
                               note='Screen cracked')
        self.assertTrue(page['ok'], page)
        self.assertEqual(page['result']['stage'], 'waiting')
        page = Visit.tech_page(HOST, visit.name, token, action='result_approved_here')
        self.assertEqual(page['result']['stage'], 'to_take')
        page = Visit.tech_page(HOST, visit.name, token, action='result_take', no_accessories=True)
        self.assertTrue(page['ok'], page)
        self.assertEqual(visit.state, 'done')
        self.assertEqual(page['result_label'], 'Repair at the office')
        late = Visit.tech_page(HOST, visit.name, token, action='result_fixed')
        self.assertEqual(late['error'], 'state')
