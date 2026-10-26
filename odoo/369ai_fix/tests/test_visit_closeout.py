# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .test_visit import HOST, DoorstepCase
from .test_visit_checks import PNG, b64


@tagged('post_install', '-at_install')
class TestVisitCloseout(DoorstepCase):
    """After "What did you find?": the labour price, "Can it be fixed?", a part asked of the
    office, two grades of a part, and Finish (after photo, payment at the door, finish code,
    receipt, rating)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['device.category'].create({'name': 'CO Phones'})
        cls.brand = cls.env['device.brand'].create({'name': 'CO Brand', 'category_id': cls.category.id})
        cls.screen_issue = cls.env['job.card.issue.type'].create({'name': 'CO Screen broken'})
        Product = cls.env['product.product']
        part = {'type': 'consu', 'is_storable': True, 'sale_ok': True,
                'repair_issue_type_ids': [(6, 0, cls.screen_issue.ids)]}
        cls.original = Product.create(dict(part, name='CO Screen original', lst_price=45.0,
                                           standard_price=20.0, fix_part_grade='original'))
        cls.compatible = Product.create(dict(part, name='CO Screen compatible', lst_price=28.0,
                                             standard_price=10.0, fix_part_grade='compatible'))
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        for product in (cls.original, cls.compatible):
            cls.env['stock.quant']._update_available_quantity(product, warehouse.lot_stock_id, 5)
        journal = cls.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', cls.env.company.id)], limit=1)
        cls.cash = cls.env['easy.sales.payment.method'].create(
            {'name': 'CO Cash', 'journal_id': journal.id, 'company_id': cls.env.company.id})
        cls.env.company.fix_warranty_days = 30
        cls.env.company.fix_review_url = 'https://g.page/r/co-test/review'

    def _working(self):
        order, visit = self._visit()
        visit.action_assign()
        link = self.sent[-1][1].split('/tech?', 1)[1].split()[0]
        token = dict(part.split('=', 1) for part in link.split('&'))['t']
        visit.action_on_the_way()
        visit._fs_arrive(skip_code=True)
        visit.with_context(fix_checks_passed=True).action_start()
        visit._vr_card(brand=self.brand, category=self.category)
        return order, visit, token

    def _texts(self, before):
        return [t for _p, t in self.sent[before:]]

    def _finishing_with_labour(self, price=15.0):
        """Labour priced at the door, quoted, approved at the door, repaired: Finish."""
        order, visit, token = self._working()
        visit._vr_set_price(price)
        visit._vr_send_quote('now')
        visit._vr_approved_here()
        visit._vr_fixed()
        self.assertEqual(visit.close_stage, 'finish')
        return order, visit, token

    # ------------------------------------------------------------------ labour price
    def test_labour_price_is_quoted_without_a_part(self):
        _order, visit, _token = self._working()
        visit._vr_set_price(15.0)
        card = visit.job_card_id
        self.assertEqual(card.service_line_ids.mapped('unit_price'), [15.0])
        self.assertTrue(visit._vr_need()['needs_quote'])
        with self.assertRaises(UserError):
            visit._vr_fixed()                                  # the customer approves the price first
        before = len(self.sent)
        visit._vr_send_quote('now')
        texts = self._texts(before)
        self.assertTrue(any('/quote?' in t and 'fixes it now' in t and 'has the part' not in t for t in texts), texts)
        self.assertEqual(card.quote_state, 'waiting')

    def test_free_fix_needs_no_quote_and_no_payment(self):
        order, visit, token = self._working()
        before = len(self.sent)
        visit._vr_fixed()
        code_msg = [t for t in self._texts(before) if visit.finish_code in t]
        self.assertTrue(code_msg, self._texts(before))
        view = visit._fs_tech_view()
        self.assertNotIn('result', view)                       # "What did you find?" is shut
        self.assertFalse(view['close']['to_pay'])
        with self.assertRaises(UserError):
            visit._co_pay(self.cash.id)
        visit._co_photo(b64(PNG))
        visit._co_free()
        self.assertTrue(visit._co_finish(code=visit.finish_code)['ok'])
        self.assertEqual(visit.state, 'done')
        self.assertIn('No charge', self.sent[-1][1])

    # ------------------------------------------------------------------ Finish
    def test_finish_photo_payment_and_code(self):
        order, visit, token = self._finishing_with_labour(15.0)
        card = visit.job_card_id
        self.assertEqual(visit._co_due(), 15.0)
        result = visit._co_finish(code=visit.finish_code)
        self.assertEqual(result['error'], 'missing')           # photo and payment first
        visit._co_photo(b64(PNG))
        with self.assertRaises(UserError):
            visit._co_pay(self.cash.id, 99)                    # more than due
        visit._co_pay(self.cash.id)
        self.assertEqual(visit.paid_amount, 15.0)
        sale = visit.pay_sale_id
        self.assertEqual(sale, card.easy_sales_id)
        self.assertEqual(sum(sale.payment_line_ids.mapped('amount')), 15.0)
        with self.assertRaises(UserError):
            visit._co_pay(self.cash.id)                        # once
        wrong = visit._co_finish(code='0000' if visit.finish_code != '0000' else '1111')
        self.assertEqual(wrong['error'], 'wrong_code')
        self.assertEqual(visit.state, 'in_progress')
        before = len(self.sent)
        self.assertTrue(visit._co_finish(code=visit.finish_code)['ok'])
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.close_stage, 'closed')
        self.assertEqual(card.state, 'completed')
        self.assertEqual(order.state, 'done')
        self.assertTrue(visit.warranty_until)
        receipt = [t for t in self._texts(before) if '/rate?' in t]
        self.assertEqual(len(receipt), 1, self._texts(before))
        self.assertIn('15', receipt[0])
        self.assertIn('CO Cash', receipt[0])
        self.assertIn('Warranty', receipt[0])
        track = self._track()
        self.assertTrue(track['close']['paid'])
        self.assertIn('/rate?', track['close']['rate_url'])

        # the rating link: stars once; 4-5 stars also get the review link
        link = receipt[0].split('/rate?', 1)[1].split()[0]
        params = dict(part.split('=', 1) for part in link.split('&'))
        Visit = self.env['fix.service.visit']
        self.assertFalse(Visit.rate_options(HOST, params['v'], 'wrong')['ok'])
        page = Visit.rate_options(HOST, visit.name, params['t'])
        self.assertFalse(page['rated'])
        self.assertFalse(Visit.rate_answer(HOST, visit.name, params['t'], 9)['ok'])
        page = Visit.rate_answer(HOST, visit.name, params['t'], 5, 'Quick and clean')
        self.assertTrue(page['rated'])
        self.assertEqual(page['review_url'], 'https://g.page/r/co-test/review')
        Visit.rate_answer(HOST, visit.name, params['t'], 1)
        self.assertEqual(visit.rating, 5)                      # rated once

    def test_finish_through_the_technician_page(self):
        _order, visit, token = self._finishing_with_labour(10.0)
        Visit = self.env['fix.service.visit']
        page = Visit.tech_page(HOST, visit.name, token)
        self.assertEqual(page['close']['due'], 10.0)
        self.assertIn(self.cash.id, [m['id'] for m in page['close']['methods']])
        blocked = Visit.tech_page(HOST, visit.name, token, action='result_note', note='x')
        self.assertEqual(blocked['error'], 'close')
        page = Visit.tech_page(HOST, visit.name, token, action='close_photo', data=b64(PNG))
        self.assertEqual(page['close']['photos'], 1)
        page = Visit.tech_page(HOST, visit.name, token, action='close_pay', method_id=self.cash.id)
        self.assertTrue(page['close']['paid'], page)
        page = Visit.tech_page(HOST, visit.name, token, action='close_code', code='x')
        self.assertEqual(page['error'], 'wrong_code')
        page = Visit.tech_page(HOST, visit.name, token, action='close_code', code=visit.finish_code)
        self.assertTrue(page['ok'], page)
        self.assertEqual(page['state'], 'done')

    def test_manager_finishes_without_the_code(self):
        _order, visit, _token = self._finishing_with_labour(10.0)
        visit._co_photo(b64(PNG))
        manager = new_test_user(self.env, login='co_manager',
                                groups='base.group_user,mobile_repair.group_mobile_repair_manager')
        with self.assertRaises(AccessError):
            visit.with_user(self.tech_user).action_finish_without_code('Customer not at home')
        with self.assertRaises(UserError):
            visit.with_user(manager).action_finish_without_code('Customer not at home')   # payment first
        visit._co_pay(self.cash.id)
        visit.with_user(manager).action_finish_without_code('Customer not at home')
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.finish_skip_reason, 'Customer not at home')

    # ------------------------------------------------------------------ can it be fixed?
    def test_no_fault_found_closes_with_the_reason(self):
        order, visit, _token = self._working()
        with self.assertRaises(UserError):
            visit._vr_outcome('no_fault')                      # the reason is required
        before = len(self.sent)
        visit._vr_outcome('no_fault', note='Works fine after a restart')
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'no_repair')
        self.assertEqual(visit.job_card_id.state, 'cancelled')
        self.assertEqual(order.state, 'done')
        texts = self._texts(before)
        self.assertTrue(any('Works fine after a restart' in t for t in texts), texts)
        self.assertFalse(any('cancelled' in t.lower() for t in texts), texts)

    def test_lab_check_takes_the_device(self):
        _order, visit, _token = self._working()
        visit._vr_outcome('lab', days=3)
        self.assertEqual(visit.check_result, 'to_take')
        before = len(self.sent)
        visit._vr_take(no_accessories=True)
        self.assertEqual(visit.check_result, 'lab')
        self.assertTrue(visit.job_card_id.wb_at_office)
        texts = self._texts(before)
        self.assertTrue(any('lab' in t and '3 days' in t for t in texts), texts)

    def test_part_not_in_the_list_goes_to_the_office(self):
        _order, visit, _token = self._working()
        before = len(self.sent)
        request = visit._vr_request_part('CO Flex cable rare', price=7.5, data=b64(PNG))
        self.assertEqual(request.state, 'requested')
        self.assertEqual(request.job_card_id, visit.job_card_id)
        self.assertEqual(request.estimated_cost, 7.5)
        self.assertTrue(self.env['ir.attachment'].search([('res_model', '=', request._name), ('res_id', '=', request.id)]))
        self.assertEqual(visit.state, 'done')
        self.assertEqual(visit.check_result, 'sourcing')
        self.assertTrue(any('CO Flex cable rare' in t for t in self._texts(before)))

    # ------------------------------------------------------------------ two grades of a part
    def test_customer_chooses_the_grade(self):
        order, visit, token = self._working()
        visit.job_card_id.issue_type_ids = self.screen_issue
        first = visit._vr_add_part(self.original)
        alts = visit._vr_alternatives(first)
        self.assertEqual([a['product_id'] for a in alts], [self.compatible.id])
        second = visit._vr_add_part(self.compatible, alt_of=first)
        card = visit.job_card_id
        self.assertEqual(first.fix_alt_key, second.fix_alt_key)
        self.assertTrue(second.fix_alt_off)
        self.assertEqual(card._wb_lines_total(), 45.0)        # the grade shown first counts
        with self.assertRaises(UserError):
            visit._vr_fixed()
        before = len(self.sent)
        visit._vr_send_quote('now')
        quote = next(t for t in self._texts(before) if '/quote?' in t)
        self.assertIn('you choose', quote)
        link = quote.split('/quote?', 1)[1].split()[0]
        params = dict(part.split('=', 1) for part in link.split('&'))
        options = order.quote_options(HOST, params['o'], params['t'])
        self.assertEqual(len(options['choices']), 1)
        self.assertEqual(len(options['choices'][0]['options']), 2)
        order.quote_answer(HOST, params['o'], params['t'], True, choice=[second.id])
        self.assertFalse(first.exists())
        self.assertEqual(card.spare_part_line_ids.product_id, self.compatible)
        self.assertEqual(card.estimate_total, 28.0)
        self.assertEqual(visit.check_result, 'repairing')

    def test_technician_keeps_one_grade_at_the_door(self):
        _order, visit, _token = self._working()
        first = visit._vr_add_part(self.original)
        second = visit._vr_add_part(self.compatible, alt_of=first)
        visit._vr_choose(second)
        self.assertFalse(first.exists())
        self.assertFalse(second.fix_alt_key)
        self.assertEqual(visit.job_card_id._wb_lines_total(), 28.0)
