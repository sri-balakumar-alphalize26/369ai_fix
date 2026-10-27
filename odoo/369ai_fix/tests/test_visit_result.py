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
        # the customer's order page: the Quotation step, though the job card is still in inspection
        order = visit.order_id
        self.assertEqual(order._timeline_index(), 3)
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
        # repaired: the visit stays open to finish (after photo, payment, the customer's code)
        self.assertEqual(visit.state, 'in_progress')
        self.assertEqual(visit.close_stage, 'finish')
        self.assertEqual(visit.check_result, 'fixed')
        self.assertFalse([t for _p, t in self.sent[before:] if '/quote?' in t])   # no quotation

    def test_parts_need_the_quotation_first(self):
        _order, visit, _token = self._working()
        wiz = self._wizard(visit, [self.in_office])
        with self.assertRaises(UserError):
            wiz.action_fixed()
        self.assertEqual(visit.state, 'in_progress')

    def test_search_offers_only_parts_for_the_device(self):
        """A phone's search for "screen" never offers a laptop screen; a part for any device does show."""
        _order, visit, _token = self._working()
        laptops = self.env['device.category'].create({'name': 'VR Laptops'})
        laptop_screen = self.env['product.product'].create({
            'name': 'VR Screen for laptops', 'type': 'consu', 'sale_ok': True, 'lst_price': 60.0,
            'fit_category_ids': [(6, 0, laptops.ids)]})
        phone_screen = self.env['product.product'].create({
            'name': 'VR Screen for phones', 'type': 'consu', 'sale_ok': True, 'lst_price': 25.0,
            'fit_category_ids': [(6, 0, self.category.ids)]})
        visit._vr_card(brand=self.brand)                          # the device: a VR Phones phone
        found = [p['product_id'] for p in visit._vr_parts('VR Screen')]
        self.assertIn(phone_screen.id, found)
        self.assertIn(self.in_office.id, found)                   # fits any device
        self.assertNotIn(laptop_screen.id, found)

    # ------------------------------------------------------------------ a part asked of the office at the door
    def test_ask_the_office_and_wait_then_found(self):
        order, visit, token = self._working()
        Visit = self.env['fix.service.visit']
        page = Visit.tech_page(HOST, visit.name, token, action='result_ask', name='VR charging flex', price=4.0,
                               brand_id=self.brand.id)
        self.assertNotEqual(page.get('ok'), False, page)
        self.assertEqual(visit.state, 'in_progress')                 # the technician waits at the door
        self.assertEqual((visit.ask_state, visit.ask_name), ('asked', 'VR charging flex'))
        self.assertEqual(page['result']['ask']['state'], 'asked')
        # the Booking Desk: the badge, the count that rings, and the two answers
        detail = order.fix_desk_detail()
        self.assertEqual(detail['ask']['name'], 'VR charging flex')
        self.assertIn('part_found', detail['actions'])
        self.assertIn('part_none', detail['actions'])
        self.assertTrue(self.env['online.service.order'].fix_desk_load(stage='working')['part_asks'] >= 1)
        # the office answers with a part from the list, at its own price
        self.env['fix.part.ask.wizard'].create({'visit_id': visit.id, 'product_id': self.in_office.id,
                                                'price': 18.0, 'note': 'In the drawer'}).action_confirm()
        line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.product_id == self.in_office)
        self.assertEqual(line.unit_price, 18.0)
        self.assertEqual(visit.ask_state, 'found')
        page = Visit.tech_page(HOST, visit.name, token)
        self.assertEqual(page['result']['ask']['part_price'], 18.0)
        self.assertEqual(page['result']['ask']['reply'], 'In the drawer')
        self.assertNotIn('part_found', order.fix_desk_detail()['actions'])     # answered: no more buttons
        # kept for good: the question and the answer, on the desk, the technician's page and the job card
        row = visit.part_ask_ids
        self.assertEqual((row.state, row.name, row.product_id, row.price, row.reply),
                         ('found', 'VR charging flex', self.in_office, 18.0, 'In the drawer'))
        self.assertEqual(row.job_card_id, visit.job_card_id)
        self.assertEqual([a['state'] for a in order.fix_desk_detail()['ask_history']], ['found'])
        self.assertEqual(page['result']['ask_history'][0]['part'], self.in_office.display_name)
        self.assertEqual(page['ask_history'][0]['state'], 'found')          # on the page at every step

    def test_ask_the_office_rings_on_every_page(self):
        """The alarm service's state lists the question (the "Technician waiting for a part" card)
        until the office answers it."""
        order, visit, _token = self._working()
        visit._vr_ask_office('VR earpiece', brand=self.brand)
        Order = self.env['online.service.order']
        asks = [a for a in Order.alarm_state()['asks'] if a['id'] == visit.id]
        self.assertEqual(len(asks), 1)
        self.assertEqual((asks[0]['order_id'], asks[0]['part']), (order.id, 'VR earpiece'))
        visit._vr_ask_found(product=self.in_office, price=7.0)
        self.assertFalse([a for a in Order.alarm_state()['asks'] if a['id'] == visit.id])

    def test_ask_the_office_new_part_or_not_available(self):
        _order, visit, _token = self._working()
        visit._vr_ask_office('VR hinge', brand=self.brand)
        with self.assertRaises(UserError):
            visit._vr_ask_found(new_name='VR hinge kit')              # a new part needs its price
        visit._vr_ask_found(new_name='VR hinge kit', price=9.0)
        part = visit.job_card_id.spare_part_line_ids.product_id.filtered(lambda p: p.name == 'VR hinge kit')
        self.assertTrue(part)
        self.assertEqual(part.fit_category_ids, self.category)        # found again for this device type only
        visit._vr_ask_office('VR rare board')
        with self.assertRaises(UserError):
            visit._vr_ask_none('')                                    # the technician reads why
        visit._vr_ask_none('No supplier for this model')
        self.assertEqual((visit.ask_state, visit.ask_reply), ('none', 'No supplier for this model'))
        # both questions kept, newest first, each with its own answer
        self.assertEqual([(a.name, a.state) for a in visit.part_ask_ids.sorted('id', reverse=True)],
                         [('VR rare board', 'none'), ('VR hinge', 'found')])
        self.assertEqual(visit.part_ask_ids.filtered(lambda a: a.state == 'none').reply, 'No supplier for this model')
        visit._vr_outcome('not_worth', note='Board not available')   # the technician closes it
        self.assertEqual(visit.state, 'done')

    def test_a_question_from_before_the_history_is_kept_when_answered(self):
        _order, visit, _token = self._working()
        visit._vr_ask_office('VR speaker', brand=self.brand)
        visit.part_ask_ids.unlink()                                   # as asked before the history was kept
        visit.ask_id = False
        visit._vr_ask_none('Out of stock everywhere')
        self.assertEqual((visit.part_ask_ids.name, visit.part_ask_ids.state), ('VR speaker', 'none'))

    def test_an_answered_question_from_before_the_history_shows_on_the_desk(self):
        order, visit, _token = self._working()
        visit._vr_ask_office('VR battery', brand=self.brand)
        visit._vr_ask_found(product=self.in_office, price=11.0, note='Shelf 2')
        visit.part_ask_ids.unlink()                                   # answered before the history was kept
        visit.ask_id = False
        history = order.fix_desk_detail()['ask_history']
        self.assertEqual([(a['name'], a['state'], a['price'], a['reply']) for a in history],
                         [('VR battery', 'found', 11.0, 'Shelf 2')])
        self.assertEqual(len(order.fix_desk_detail()['ask_history']), 1)       # made once only

    def test_ask_the_office_then_dont_wait(self):
        _order, visit, _token = self._working()
        visit._vr_ask_office('VR mic flex', price=3.0, brand=self.brand)
        visit._vr_request_part('')                                    # "Don't wait": the question's own part
        self.assertEqual((visit.state, visit.check_result), ('done', 'sourcing'))
        self.assertFalse(visit.ask_state)
        request = self.env['spare.part.purchase.request'].search([('product_name', '=', 'VR mic flex')])
        self.assertEqual(request.estimated_cost, 3.0)
        self.assertEqual(visit.part_ask_ids.state, 'later')               # kept: the office finds it later
        self.assertIn(request.name, visit.part_ask_ids.reply)

    # ------------------------------------------------------------------ Labour only: free, or a charge with the customer's OK
    def test_labour_only_is_free_by_default(self):
        order, visit, _token = self._working()
        visit._vr_outcome('labour', brand=self.brand)
        card = visit.job_card_id
        self.assertTrue(card)
        self.assertEqual(card._wb_lines_total(), 0.0)
        self.assertFalse(visit._vr_need()['needs_quote'])
        self.assertEqual(visit._vr_view()['labour'], 'free')
        self.assertEqual(order._fix_desk_row()['labour'], 'free')          # the office's note
        visit._vr_fixed()                                                    # no quotation needed
        self.assertEqual(visit.check_result, 'fixed')

    def test_a_labour_charge_needs_the_customers_ok(self):
        order, visit, _token = self._working()
        visit._vr_outcome('labour', brand=self.brand)
        visit._vr_labour_charge(15)
        card = visit.job_card_id
        labour = card.service_line_ids.filtered(lambda l: l.product_id.default_code == 'REPAIR-SERVICE')
        self.assertEqual(labour.mapped('unit_price'), [15.0])
        self.assertTrue(visit._vr_need()['needs_quote'])
        with self.assertRaises(UserError):
            visit._vr_fixed()                                                # the customer approves first
        visit._vr_send_quote('now')
        text, _total = order._wb_estimate()
        self.assertIn('Labour', text)
        visit._vr_approved_here()
        self.assertEqual(visit.check_result, 'repairing')
        self.assertEqual(order._fix_desk_row()['labour'], 15.0)
        visit._vr_fixed()
        self.assertEqual(visit.check_result, 'fixed')

    def test_labour_back_to_free_and_back_to_parts(self):
        _order, visit, _token = self._working()
        card = visit._vr_card(brand=self.brand)
        booked = self.env['product.product'].create({'name': 'VR Booked repair', 'type': 'service', 'lst_price': 30.0})
        self.env['job.card.service.line'].create({'job_card_id': card.id, 'product_id': booked.id,
                                                   'description': booked.name, 'quantity': 1, 'unit_price': 30.0})
        visit._vr_outcome('labour')
        self.assertEqual(card.service_line_ids.mapped('unit_price'), [0.0])  # free: the booked repair at 0
        text, _total = visit.order_id._wb_estimate()
        self.assertNotIn('VR Booked repair', text)                           # the customer reads only what is charged
        visit._vr_labour_charge(10)
        visit._vr_labour_charge(0)                                           # free again: the labour line goes
        self.assertFalse(card.service_line_ids.filtered(lambda l: l.product_id.default_code == 'REPAIR-SERVICE'))
        visit._vr_outcome('parts')                                           # back to the booked price
        self.assertEqual(card.service_line_ids.mapped('unit_price'), [30.0])

    def test_a_fixed_labour_price_is_one_tap_at_this_devices_price(self):
        """Catalogue > Labour Prices: the technician taps "Cleaning"; the price is the device type's
        own row, else the price for every device - always the office's, never the phone's."""
        _order, visit, token = self._working()
        laptops = self.env['device.category'].create({'name': 'VR Laptops'})
        service = self.env['product.template'].create({'name': 'VR Cleaning', 'type': 'service', 'list_price': 20.0})
        cleaning = self.env['fix.labour.job'].create({
            'service_id': service.id, 'price': 3.0,
            'price_ids': [(0, 0, {'category_id': laptops.id, 'price': 8.0})]})
        self.assertEqual(cleaning.name, 'VR Cleaning')                       # the service picked from the list
        self.assertEqual(cleaning._price_for(laptops), 8.0)
        self.assertEqual(cleaning._price_for(self.category), 3.0)
        self.assertEqual(service.list_price, 20.0)                           # the website price stays
        visit._vr_outcome('labour', brand=self.brand)                        # a VR Phones phone
        presets = [p for p in visit._vr_view()['labour_presets'] if p['id'] == cleaning.id]
        self.assertEqual([p['price'] for p in presets], [3.0])
        page = self.env['fix.service.visit'].tech_page(HOST, visit.name, token, action='result_labour',
                                                       preset_id=cleaning.id, price=99, brand_id=self.brand.id)
        self.assertNotEqual(page.get('ok'), False, page)
        labour = visit._vr_labour_lines()
        self.assertEqual([(l.description, l.unit_price) for l in labour], [('VR Cleaning', 3.0)])
        self.assertEqual(visit._vr_labour_note(), 3.0)
        self.assertTrue(visit._vr_need()['needs_quote'])                     # the customer approves it first
        visit._vr_labour_charge(5)                                           # typed instead: plain "Labour"
        self.assertEqual([(l.description, l.unit_price) for l in visit._vr_labour_lines()], [('Labour', 5.0)])
        visit._vr_labour_charge(0)
        self.assertFalse(visit._vr_labour_lines())
        cleaning.active = False                                              # archived: no tap
        with self.assertRaises(UserError):
            visit._vr_labour_preset(cleaning.id)

    # ------------------------------------------------------------------ a device at our office
    def test_lab_take_receipt_received_and_overdue(self):
        order, visit, _token = self._working()
        charger = self.env['device.accessory'].create({'name': 'VR Charger'})
        visit._vr_outcome('lab', days=2, brand=self.brand)
        visit._vr_approved_here()                                            # the customer agreed at the door
        before = len(self.sent)
        visit._vr_take(accessories=charger)
        card = visit.job_card_id
        texts = [t for _p, t in self.sent[before:]]
        self.assertTrue(any('VR Charger' in t for t in texts), texts)        # the customer's receipt
        self.assertTrue(card.wb_price_by)                                    # the price promised by
        # the desk: on the way to the office, until the office presses Received
        self.assertEqual(order._fix_desk_row()['office'], 'on_way')
        self.assertEqual(order._fix_desk_stage(), 'working')
        self.assertIn('office_received', order.fix_desk_detail()['actions'])
        self.assertEqual(order._wb_office_row()['accessories'], '1 accessory (VR Charger)')
        self.env['wb.receive.wizard'].create({'job_card_id': card.id, 'accessory_ids': [(6, 0, [])],
                                              'note': 'Scratch on the back'}).action_confirm()
        self.assertEqual(card._wb_office_state(), 'received')
        self.assertEqual(card.wb_received_by_id, self.env.user)
        self.assertIn('Missing 1: VR Charger', ' '.join(card.message_ids.mapped('body')))
        self.assertEqual(order._wb_office_row()['accessories'], '1 accessory (VR Charger)')   # counted
        self.assertNotIn('office_received', order.fix_desk_detail()['actions'])
        self.assertTrue(order._wb_office_row()['received'])
        # the promised price date passed: Overdue, and one to-do however often the job runs
        yesterday = fields.Date.add(fields.Date.context_today(card), days=-1)
        card.wb_price_by = yesterday
        self.assertEqual(card._wb_overdue(), 'price')
        self.assertEqual(order._fix_desk_row()['overdue'], 'price')
        Card = self.env['job.card']
        Card._cron_wb_overdue()
        Card._cron_wb_overdue()
        todos = card.activity_ids.filtered(lambda a: 'Overdue: send the price' in (a.summary or ''))
        self.assertEqual(len(todos), 1)
        # the price approved, the return date passed: Overdue (return)
        card.write({'quote_state': 'accepted', 'wb_return_by': yesterday})
        self.assertEqual(card._wb_overdue(), 'return')

    def test_the_customer_approves_the_price_on_my_orders(self):
        """The new price on My orders (signed in), as on the WhatsApp link's page: Review, Approve."""
        from .test_visit import PHONE
        order, visit, _token = self._working()
        self._quote(visit, [self.in_office], plan_here='come_back', days=2)
        Order = self.env['online.service.order']
        row = [r for r in Order.customer_orders(HOST, PHONE)['orders'] if r['ref'] == order.name][0]
        self.assertEqual(row['quote']['state'], 'waiting')                  # "Review & approve" on the order
        page = Order.customer_quote(HOST, PHONE, order.name)
        self.assertEqual(page['state'], 'waiting')
        self.assertTrue(page['lines'])
        # another number cannot see or answer it
        self.assertEqual(Order.customer_quote(HOST, '+968 9999 0000', order.name)['error'], 'unknown')
        done = Order.customer_quote(HOST, PHONE, order.name, action='answer', yes=True)
        self.assertEqual(done['state'], 'accepted')
        self.assertEqual(visit.job_card_id.quote_state, 'accepted')
        self.assertEqual(visit.check_result, 'come_back')                   # the plan went ahead
        row = [r for r in Order.customer_orders(HOST, PHONE)['orders'] if r['ref'] == order.name][0]
        self.assertIsNone(row['quote'])                                     # nothing left to answer

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
        self.assertEqual(visit.close_stage, 'finish')
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
        self.assertNotIn('result', found)          # searched as you type: the parts only, not the whole page
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

    # ------------------------------------------------------------------ what's wrong -> the parts for it
    def test_problems_filter_the_parts(self):
        Issue = self.env['job.card.issue.type']
        screen = Issue.create({'name': 'VR Screen broken', 'device_category_ids': [(6, 0, self.category.ids)]})
        battery = Issue.create({'name': 'VR Battery weak', 'device_category_ids': [(6, 0, self.category.ids)]})
        laptops = self.env['device.category'].create({'name': 'VR Laptops'})
        hinge = Issue.create({'name': 'VR Hinge loose', 'device_category_ids': [(6, 0, laptops.ids)]})
        self.in_office.repair_issue_type_ids = screen
        laptop_screen = self.env['product.product'].create({
            'name': 'VR Laptop screen', 'type': 'consu', 'sale_ok': True, 'lst_price': 50.0,
            'repair_issue_type_ids': [(6, 0, screen.ids)], 'fit_category_ids': [(6, 0, laptops.ids)]})

        order, visit, token = self._working()
        Visit = self.env['fix.service.visit']
        page = Visit.tech_page(HOST, visit.name, token)
        self.assertEqual(page['result']['suggested'], [])                 # nothing ticked yet
        # no job card and no brand yet: the brand comes first
        refused = Visit.tech_page(HOST, visit.name, token, action='result_issue', issue_id=screen.id, on=True)
        self.assertEqual(refused['error'], 'result')
        page = Visit.tech_page(HOST, visit.name, token, action='result_issue', issue_id=screen.id, on=True,
                               brand_id=self.brand.id)
        self.assertTrue(page['ok'], page)
        card = visit.job_card_id
        self.assertEqual(card.issue_type_ids, screen)
        # only this device type's problems, the ticked one first
        issues = page['result']['issues']
        self.assertEqual((issues[0]['id'], issues[0]['on']), (screen.id, True))
        ids = [i['id'] for i in issues]
        self.assertIn(battery.id, ids)
        self.assertNotIn(hinge.id, ids)
        # only the parts that fix it and fit a phone
        self.assertEqual([p['product_id'] for p in page['result']['suggested']], [self.in_office.id])
        self.assertNotIn(laptop_screen.id, [p['product_id'] for p in page['result']['suggested']])
        page = Visit.tech_page(HOST, visit.name, token, action='result_add_part', product_id=self.in_office.id)
        self.assertEqual(page['result']['suggested'], [])                 # added: no longer offered
        # the last problem stays when nothing else describes the fault
        card.issue = False
        with self.assertRaises(UserError):
            visit._vr_set_issue(screen, False)
        # the customer is told what was found, with the price
        before = len(self.sent)
        page = Visit.tech_page(HOST, visit.name, token, action='result_quote', plan='now')
        self.assertTrue(page['ok'], page)
        self.assertTrue(any('We found: VR Screen broken' in t for _p, t in self.sent[before:]), self.sent[before:])
        link = next(t for _p, t in self.sent[before:] if '/quote?' in t).split('/quote?', 1)[1].split()[0]
        quote_token = dict(part.split('=', 1) for part in link.split('&'))['t']
        found = self.env['online.service.order'].quote_options(HOST, order.name, quote_token)
        self.assertEqual(found['found'], ['VR Screen broken'])

    def test_part_problems_from_names(self):
        from ..repair.part_problems import fill_part_problems, guess_part
        problems, devices = guess_part('iPhone 13 Screen OLED')
        self.assertIn('Screen Cracked / Broken Display', problems)
        self.assertEqual(devices, ['Mobile Phone'])
        self.assertEqual(guess_part('Laptop Stand Adjustable'), ([], []))     # not a part
        self.assertEqual(guess_part('ASUS RT-AX1800S Dual Band')[0], [])        # a router, not a watch band
        Template = self.env['product.template']
        laptop_screen = Template.create({'name': 'VR HP 15.6 inch Laptop Screen', 'type': 'consu'})
        kept = Template.create({'name': 'VR Phone Battery', 'type': 'consu'})
        own = self.env['job.card.issue.type'].create({'name': 'VR Own choice'})
        kept.repair_issue_type_ids = own
        fill_part_problems(self.env)
        names = laptop_screen.repair_issue_type_ids.mapped('name')
        self.assertIn('Screen Cracked / Broken Display', names)
        self.assertNotIn('Touch Not Working', names)                          # not a laptop's problem
        self.assertEqual(laptop_screen.fit_category_ids.mapped('name'), ['Laptop'])
        self.assertEqual(kept.repair_issue_type_ids, own)                    # staff's choice kept
