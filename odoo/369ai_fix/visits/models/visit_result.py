# -*- coding: utf-8 -*-
"""What the technician found, and the quotation first - as on Urban Company.

While the visit is Working the technician ticks the problems found (the customer's
choice is ticked already) and is offered the parts that fix them for this device; the
search box finds any other part. Each part shows whether the office has it, another
branch has it, or it must be ordered.

* No part, no extra price: Fixed on the spot.
* Parts / a higher price: the QUOTATION goes to the customer first, with the plan and
  its timeline (fix now / take to the office, back by a date / we come back within N days /
  the part must be ordered, about X days). Nothing is repaired, taken or ordered before
  the customer's OK - on the WhatsApp link, by phone, or at the door to the technician.
  Approved: the plan goes ahead (an ordered part is ordered by the quotation itself,
  booking/). Declined: nothing done; with "Visit fee + quote" only the visit fee is billed.
  No answer while the technician is there: "decide later" closes the visit.

The parts are the job card's own spare lines, so the existing quotation, ordering,
part-arrived and return-visit flows (booking/) carry on unchanged. A visit without a
job card gets one here (the device brand is asked when the booking had none).

"Can it be fixed?" comes first: needs parts / labour only (both priced here: the labour
price can be typed, and any price above what the customer agreed is quoted first, part or
not) / needs a lab check (the device goes to the office, the price follows) / no fault /
not worth repairing / under the brand's warranty (the visit closes with the reason).
A part that is not in the list is asked of the office (a purchase request, priced there).
A part can be offered in two grades (original / compatible): the customer keeps one.
"""
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .visit_checks import PHOTO_BYTES, _sniff

RESULTS = [
    ('fixed', 'Fixed on the spot'),
    ('waiting', "Quotation sent: waiting for the customer's OK"),
    ('repairing', 'Approved: repairing now'),
    ('to_take', 'Approved: take the device to the office'),
    ('office', 'Repair at the office'),
    ('come_back', 'We come back with the part'),
    ('ordered', 'Approved: part ordered'),
    ('quoted', 'Quotation sent: customer decides later'),
    ('declined', 'Customer declined the quotation'),
    ('sourcing', 'Part asked of the office: price follows'),
    ('lab', 'Taken to the lab for a check'),
    ('no_repair', 'Not repaired'),
]
# "Can it be fixed?" - the technician's first answer
OUTCOMES = [
    ('parts', 'Needs parts'),
    ('labour', 'Labour only'),
    ('lab', 'Needs lab check'),
    ('no_fault', 'No fault found'),
    ('not_worth', 'Not worth repairing'),
    ('warranty', "Under the brand's warranty"),
]
NO_REPAIR = ('no_fault', 'not_worth', 'warranty')
# not repaired, but the visit fee is charged when Repair Settings' switch is on (paid at the door, then the code)
FEE_OUTCOMES = ('no_fault', 'not_worth')
MAX_PRICE = 100000.0
# What the technician proposes with the quotation
PLANS = [
    ('now', 'Fix now (the technician has the part)'),
    ('take', 'Take the device to the office'),
    ('come_back', 'Customer keeps it, we come back'),
    ('keep', 'Customer keeps it until the part arrives'),
    ('order_take', 'Take the device to the office until the part arrives'),
]
MAX_DAYS = 60
# A part not in the list, asked of the office while the technician waits at the door
ASK_STATES = [
    ('asked', 'Asked: waiting for the office'),
    ('found', 'Office added the part'),
    ('none', 'Office: not available'),
]


def _unit(value):
    return 'weeks' if value == 'weeks' else 'days'


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    check_result = fields.Selection(RESULTS, 'Result', readonly=True, copy=False, tracking=True)
    check_outcome = fields.Selection(OUTCOMES, 'Can it be fixed?', readonly=True, copy=False, tracking=True)
    check_found = fields.Text('What the technician found', copy=False)
    check_days = fields.Integer('Fixed within (days)', readonly=True, copy=False)
    check_result_on = fields.Datetime('Result on', readonly=True, copy=False)
    # the plan sent with the quotation, carried out once the customer approves
    pend_plan = fields.Selection(PLANS, 'Proposed', readonly=True, copy=False)
    pend_days = fields.Integer(readonly=True, copy=False)
    pend_within = fields.Char(readonly=True, copy=False)
    pend_part_days = fields.Integer(readonly=True, copy=False)
    pend_date = fields.Date('Back by', readonly=True, copy=False)
    # the part asked of the office at the door, and the office's answer
    # Labour only: the technician chose Free or a charge (no default: Fixed on the spot waits for it)
    labour_set = fields.Boolean('Labour charge chosen', readonly=True, copy=False)
    ask_state = fields.Selection(ASK_STATES, 'Part asked', readonly=True, copy=False, index=True, tracking=True)
    ask_name = fields.Char('Part asked for', readonly=True, copy=False)
    ask_price = fields.Float('Rough price (technician)', readonly=True, copy=False)
    ask_photo = fields.Binary('Photo of the part', attachment=True, readonly=True, copy=False)
    ask_on = fields.Datetime('Asked on', readonly=True, copy=False)
    ask_reply = fields.Text("Office's answer", readonly=True, copy=False)
    ask_product_id = fields.Many2one('product.product', 'Part added by the office', readonly=True, copy=False)
    ask_replied_by_id = fields.Many2one('res.users', 'Answered by', readonly=True, copy=False)
    ask_replied_on = fields.Datetime('Answered on', readonly=True, copy=False)
    # every question and its answer, kept (the fields above only hold the one open now)
    ask_id = fields.Many2one('fix.part.ask', 'Question now', readonly=True, copy=False)
    part_ask_ids = fields.One2many('fix.part.ask', 'visit_id', 'Part questions', readonly=True)

    # ------------------------------------------------------------------ the job card
    def _vr_device_guess(self):
        """(category, brand, series, model) from the booking's lines, when it has them."""
        self.ensure_one()
        line = self.sudo().order_id.line_ids.filtered('brand_id')[:1]
        return line.category_id, line.brand_id, line.series_id, line.model_id

    def _vr_card(self, brand=None, model=None, category=None):
        """The visit's job card; made here (like the booking's own) when there is none."""
        self.ensure_one()
        visit = self.sudo()
        if visit.job_card_id:
            return visit.job_card_id
        order = visit.order_id
        if not order:
            raise UserError(_("This visit has no booking: make the job card from the job card menu."))
        g_cat, g_brand, g_series, g_model = visit._vr_device_guess()
        brand = brand or g_brand
        if not brand:
            raise UserError(_("Choose the device's brand first: there is no job card yet."))
        model = model or (g_model if brand == g_brand else self.env['device.model'])
        category = category or (g_cat if brand == g_brand else self.env['device.category'])
        company = visit.company_id or self.env.company
        technician = visit.technician_id or company._wb_unassigned_employee()
        partner = order.partner_id or order._find_or_create_partner()
        lines = order.line_ids.filtered('product_id')
        ticked = visit._vr_ticked()
        issue = [order.problem or order.summary or '']
        if visit.check_found:
            issue.append(visit.check_found)
        card = self.env['job.card'].sudo().with_company(company).with_context(web_booking_auto=True).create({
            'partner_id': partner.id,
            'company_id': company.id,
            'assigned_to': technician.id,
            'delivery_type': 'door_step',
            'device_category_id': category.id or brand.category_id.id or False,
            'brand_id': brand.id,
            'series_id': (model.series_id.id if model else False) or (g_series.id if brand == g_brand else False),
            'model_id': model.id or False,
            'issue': '\n'.join(x for x in issue if x) or _("Doorstep visit %s", visit.name),
            'issue_type_ids': [(6, 0, ticked.ids)],
            'service_line_ids': [(0, 0, {
                'product_id': line.product_id.id, 'description': line.product_id.name,
                'quantity': line.qty or 1, 'unit_price': line.product_id.lst_price,
            }) for line in lines],
            'online_order_id': order.id,
        })
        # quietly: the customer hears the result itself, not "inspecting your device" just before it
        card.with_context(wb_silent=True).write({'state': 'inspection', 'inspection_date': fields.Date.context_today(self)})
        visit.job_card_id = card
        if not order.job_card_id:
            order.job_card_id = card
        visit.message_post(body=_("Job card %s made for the technician's result.", card.name),
                           subtype_xmlid='mail.mt_note')
        return card

    # ------------------------------------------------------------------ parts and stock
    def _vr_office_warehouses(self):
        self.ensure_one()
        return self.env['stock.warehouse'].sudo().search([('company_id', '=', (self.company_id or self.env.company).id)])

    def _vr_stock(self, product, qty=1.0):
        """Where the part is: {office, other, status, branches} - status in_stock (this
        office), other_branch, or order."""
        self.ensure_one()
        quants = self.env['stock.quant'].sudo().search([('product_id', '=', product.id),
                                                       ('location_id.usage', '=', 'internal')])
        office_whs = self._vr_office_warehouses()
        by_wh = {}
        for quant in quants:
            wh = quant.location_id.warehouse_id
            if wh:
                by_wh[wh] = by_wh.get(wh, 0.0) + quant.quantity
        office = sum(q for wh, q in by_wh.items() if wh in office_whs)
        other = sum(q for wh, q in by_wh.items() if wh not in office_whs)
        need = qty or 1.0
        status = 'in_stock' if office >= need else 'other_branch' if office + other >= need else 'order'
        return {
            'office': office, 'other': other, 'status': status,
            'branches': [{'name': wh.name, 'qty': q} for wh, q in by_wh.items() if q > 0],
        }

    def _vr_device(self):
        """(category, brand, model) of the device: the job card's, else the booking's."""
        self.ensure_one()
        card = self.sudo().job_card_id
        if card:
            return card.device_category_id or card.brand_id.category_id, card.brand_id, card.model_id
        category, brand, _series, model = self._vr_device_guess()
        # no brand booked: the device type the customer chose still narrows the parts
        return category or brand.category_id or self.sudo().order_id.line_ids.category_id[:1], brand, model

    @staticmethod
    def _vr_rank(brand, model):
        """Sort key for parts: this model's own first, then this brand's, then the rest."""
        def rank(p):
            return (0 if model and p.device_model_id == model else 1 if brand and p.device_brand_id == brand
                    else 2, 0 if p.is_mobile_repair_part else 1, p.name or '')
        return rank

    @staticmethod
    def _vr_fit_domain(category, brand, model):
        """Parts that fit this device: each of the part's device type / brand / model is empty
        (fits any) or this device's - a phone's search never offers a laptop screen."""
        domain = []
        if category:
            domain += ['|', ('fit_category_ids', '=', False), ('fit_category_ids', 'in', category.ids)]
        if brand:
            domain += ['|', ('device_brand_id', '=', False), ('device_brand_id', '=', brand.id)]
        if model:
            domain += ['|', ('device_model_id', '=', False), ('device_model_id', '=', model.id)]
        return domain

    def _vr_parts(self, query='', limit=20):
        """Spare parts for the search box: only those that fit the device (the customer's
        device type, brand and model), its own first, each with its stock."""
        self.ensure_one()
        query = (query or '').strip()
        category, brand, model = self._vr_device()
        domain = [('type', '=', 'consu'), ('sale_ok', '=', True)] + self._vr_fit_domain(category, brand, model)
        if query:
            domain += ['|', '|', ('name', 'ilike', query), ('default_code', 'ilike', query),
                       ('barcode', '=', query)]
        products = self.env['product.product'].sudo().search(domain, limit=200)
        return [self._vr_part_row(p) for p in sorted(products, key=self._vr_rank(brand, model))[:limit]]

    # ------------------------------------------------------------------ what's wrong (as on Urban Company)
    def _vr_ticked(self):
        """The problems ticked so far: the job card's, which the booking filled with what the
        customer chose (the booking's repairs, while there is no job card)."""
        self.ensure_one()
        visit = self.sudo()
        if visit.job_card_id:
            return visit.job_card_id.issue_type_ids
        return visit.order_id.line_ids.product_id.repair_issue_type_ids

    def _vr_issues(self):
        """The problems the technician can tick: this device type's (and those for every
        device), the ticked ones first."""
        self.ensure_one()
        category = self._vr_device()[0]
        domain = ['|', ('device_category_ids', '=', False),
                  ('device_category_ids', 'in', category.ids)] if category else []
        ticked = self._vr_ticked()
        issues = ticked | self.env['job.card.issue.type'].sudo().search(domain)
        return [{'id': i.id, 'name': i.name, 'on': i in ticked} for i in issues]

    def _vr_set_issue(self, issue, on, brand=None):
        """Tick / untick a problem on the job card (made here when there is none yet)."""
        self.ensure_one()
        card = self._vr_card(brand=brand)
        if on:
            card.issue_type_ids = [(4, issue.id)]
        elif issue in card.issue_type_ids:
            if card.issue_type_ids == issue and not (card.issue or '').strip():
                raise UserError(_("Keep at least one problem ticked, or write what you found first."))
            card.issue_type_ids = [(3, issue.id)]

    def _vr_suggest(self, limit=12):
        """The parts that fix the ticked problems and fit this device (this model's own
        first), leaving out those already added."""
        self.ensure_one()
        ticked = self._vr_ticked()
        if not ticked:
            return []
        category, brand, model = self._vr_device()
        domain = [('type', '=', 'consu'), ('sale_ok', '=', True), ('repair_issue_type_ids', 'in', ticked.ids)] \
            + self._vr_fit_domain(category, brand, model)
        products = self.env['product.product'].sudo().search(domain, limit=200)
        card = self.sudo().job_card_id
        if card:
            products -= card.spare_part_line_ids.product_id
        return [self._vr_part_row(p) for p in sorted(products, key=self._vr_rank(brand, model))[:limit]]

    def _vr_part_row(self, product, qty=1.0):
        stock = self._vr_stock(product, qty)
        grades = dict(self.env['product.template']._fields['fix_part_grade'].selection)
        return {'product_id': product.id, 'name': product.display_name, 'price': product.lst_price,
                'grade': grades.get(product.fix_part_grade, ''),
                'office': stock['office'], 'other': stock['other'], 'status': stock['status'],
                'branches': stock['branches']}

    def _vr_lines(self):
        """The parts on the job card, each with where it is. Two grades offered for one part
        share `alt_key`; `alt_off` is the grade not chosen (yet)."""
        self.ensure_one()
        card = self.sudo().job_card_id
        rows = []
        for line in card.spare_part_line_ids.sorted(lambda l: (l.fix_alt_key or 'A%d' % l.id, l.fix_alt_off, l.id)) \
                if card else []:
            row = self._vr_part_row(line.product_id, line.quantity)
            row.update(line_id=line.id, qty=line.quantity, name=line.description or line.product_id.display_name,
                       price=line.unit_price, alt_key=line.fix_alt_key or '', alt_off=line.fix_alt_off,
                       can_alt=bool(line.product_id.fix_part_grade) and not line.fix_alt_key)
            rows.append(row)
        return rows

    def _vr_add_part(self, product, qty=1.0, brand=None, model=None, category=None, alt_of=None):
        """A part on the job card. `alt_of`: a line already there - this part is another grade
        of it, offered beside it (the customer keeps one; the first stays chosen)."""
        self.ensure_one()
        card = self._vr_card(brand=brand, model=model, category=category)
        line = card.spare_part_line_ids.filtered(lambda l: l.product_id == product)[:1]
        if line:
            line.quantity = qty or line.quantity
            return line
        vals = {
            'job_card_id': card.id, 'product_id': product.id, 'description': product.name,
            'quantity': qty or 1.0, 'unit_price': product.lst_price,
            'tax_ids': [(6, 0, product.taxes_id.filtered(lambda t: t.company_id == card.company_id).ids)],
        }
        if alt_of:
            if alt_of.job_card_id != card:
                raise UserError(_("That part is not on this job card."))
            key = alt_of.fix_alt_key or 'A%d' % alt_of.id
            alt_of.fix_alt_key = key
            vals.update(fix_alt_key=key, fix_alt_off=True)
        return self.env['job.card.spare.part.line'].sudo().create(vals)

    def _vr_alternatives(self, line, limit=8):
        """Other grades of a part on the card: parts that fix the same problems for this device,
        with a grade other than this one's."""
        self.ensure_one()
        product = line.product_id
        if not product.fix_part_grade or not product.repair_issue_type_ids:
            return []
        category, brand, model = self._vr_device()
        domain = [('type', '=', 'consu'), ('sale_ok', '=', True), ('id', '!=', product.id),
                  ('fix_part_grade', 'not in', (False, product.fix_part_grade)),
                  ('repair_issue_type_ids', 'in', product.repair_issue_type_ids.ids)] \
            + self._vr_fit_domain(category, brand, model)
        products = self.env['product.product'].sudo().search(domain, limit=100)
        products -= line.job_card_id.spare_part_line_ids.product_id
        return [self._vr_part_row(p) for p in sorted(products, key=self._vr_rank(brand, model))[:limit]]

    def _vr_choose(self, line):
        """The customer chose this grade at the door: the other grade is removed."""
        self.ensure_one()
        if not line.fix_alt_key:
            return True
        line.job_card_id._wb_choose_alts([line.id])
        return True

    def _vr_remove_part(self, line):
        """Remove a part; when it was the chosen grade of two, the other one becomes the part."""
        key, card = line.fix_alt_key, line.job_card_id
        line.unlink()
        if key:
            rest = card.spare_part_line_ids.filtered(lambda l: l.fix_alt_key == key)
            if len(rest) <= 1:
                rest.write({'fix_alt_key': False, 'fix_alt_off': False})
            elif not rest.filtered(lambda l: not l.fix_alt_off):
                rest[:1].fix_alt_off = False

    # ------------------------------------------------------------------ the labour (repairs) and its price
    def _vr_services(self):
        """The repairs on the job card with their price ({line_id, product_id, name, qty, price});
        the booking's while there is no job card yet (line_id 0)."""
        self.ensure_one()
        visit = self.sudo()
        card = visit.job_card_id
        if card:
            return [{'line_id': l.id, 'product_id': l.product_id.id, 'name': l.description or l.product_id.name,
                     'qty': l.quantity, 'price': l.unit_price} for l in card.service_line_ids]
        return [{'line_id': 0, 'product_id': l.product_id.id, 'name': l.product_id.name or l.issue,
                 'qty': l.qty or 1, 'price': l.product_id.lst_price}
                for l in visit.order_id.line_ids.filtered('product_id')]

    @api.model
    def _vr_labour_product(self, company):
        """The plain repair service - the same one mobile_repair's invoice puts the repairs on."""
        Product = self.env['product.product'].sudo()
        product = Product.search([('default_code', '=', 'REPAIR-SERVICE'),
                                  ('company_id', 'in', [company.id, False])], limit=1)
        return product or Product.create({'name': 'Repair Service', 'default_code': 'REPAIR-SERVICE',
                                          'type': 'service', 'sale_ok': True, 'purchase_ok': False,
                                          'list_price': 0})

    def _vr_set_price(self, price, line_id=0, product_id=0, brand=None):
        """The technician's price for a repair (labour). `line_id`: a repair on the job card;
        `product_id`: a repair of the booking (before there is a job card); neither: a labour
        line is added. A price above what the customer agreed is quoted before the repair."""
        self.ensure_one()
        try:
            price = round(float(price), 6)
        except (TypeError, ValueError):
            raise UserError(_("Type the price."))
        if not 0 <= price <= MAX_PRICE:
            raise UserError(_("Type a price of 0 or more."))
        card = self._vr_card(brand=brand)
        lines = card.service_line_ids
        line = lines.browse()
        if line_id:
            line = lines.filtered(lambda l: l.id == int(line_id))
            if not line:
                raise UserError(_("That repair is not on the job card."))
        elif product_id:
            line = lines.filtered(lambda l: l.product_id.id == int(product_id))[:1]
        if line:
            line.unit_price = price
            return line
        product = self.env['product.product'].sudo().browse(int(product_id or 0)).exists()
        if product.type != 'service':
            product = self._vr_labour_product(card.company_id)
        return self.env['job.card.service.line'].sudo().create({
            'job_card_id': card.id, 'product_id': product.id,
            'description': product.name if product.default_code != 'REPAIR-SERVICE' else _("Labour"),
            'quantity': 1.0, 'unit_price': price,
            'tax_ids': [(6, 0, product.taxes_id.filtered(lambda t: t.company_id == card.company_id).ids)],
        })

    # ------------------------------------------------------------------ Labour only: free, or a charge the customer approves
    @staticmethod
    def _vr_is_labour_line(line):
        return line.product_id.default_code == 'REPAIR-SERVICE'

    def _vr_labour_lines(self):
        self.ensure_one()
        card = self.sudo().job_card_id
        return card.service_line_ids.filtered(self._vr_is_labour_line) if card else self.env['job.card.service.line']

    def _vr_labour_free(self, brand=None):
        """Labour only: the booked repairs at 0, no labour line - and nothing chosen yet. The
        technician then picks Free or a charge (`_vr_labour_charge`, `labour_set`); a charge is
        quoted to the customer first."""
        self.ensure_one()
        visit = self.sudo()
        card = visit._vr_card(brand=brand)
        card.service_line_ids.filtered(self._vr_is_labour_line).unlink()
        card.service_line_ids.write({'unit_price': 0.0})
        visit.labour_set = False
        visit.message_post(body=_("Labour only: free or a charge, to be chosen."), subtype_xmlid='mail.mt_note')

    def _vr_labour_restore(self):
        """Back to Needs parts: the booked repairs at their own price again, no labour line."""
        self.ensure_one()
        visit = self.sudo()
        card = visit.job_card_id
        if not card:
            return
        card.service_line_ids.filtered(self._vr_is_labour_line).unlink()
        for line in card.service_line_ids:
            line.unit_price = line.product_id.lst_price
        visit.message_post(body=_("Needs parts: the booked repairs are back at their price."),
                           subtype_xmlid='mail.mt_note')

    def _vr_labour_presets(self):
        """The office's fixed labour prices (Catalogue > Labour Prices) for this device type, at its price."""
        self.ensure_one()
        visit = self.sudo()
        company = visit.company_id or self.env.company
        category = visit._vr_device()[0]
        jobs = self.env['fix.labour.job'].sudo().search([('service_id.company_id', 'in', [company.id, False])])
        return [{'id': j.id, 'name': j.name, 'price': j._price_for(category)} for j in jobs if j._fits(category)]

    def _vr_labour_preset(self, preset_id, brand=None):
        """The technician tapped a fixed labour price: its name and price come from the office's list."""
        self.ensure_one()
        job = self.env['fix.labour.job'].sudo().browse(int(preset_id or 0)).exists()
        if not job or not job.active:
            raise UserError(_("That labour price is not in the list any more."))
        category = self.sudo()._vr_device()[0]
        if not job._fits(category):
            raise UserError(_("%(job)s is not for a %(device)s.", job=job.name, device=category.name))
        price = job._price_for(category)
        return self._vr_labour_charge(price, brand=brand, name=job.name)

    def _vr_labour_charge(self, amount, brand=None, name=None):
        """Labour only, a charge: one "Labour" line at this amount (0 = free again). Any charge is
        quoted first - the customer approves it before the repair (`_vr_need`). `name`: a fixed
        labour price's job (e.g. Cleaning), shown on the line instead of "Labour"."""
        self._vr_require()
        if self.check_outcome != 'labour':
            raise UserError(_("Choose \"Labour only\" first."))
        try:
            amount = round(float(amount or 0.0), 6)
        except (TypeError, ValueError):
            raise UserError(_("Type the labour charge."))
        if not 0 <= amount <= MAX_PRICE:
            raise UserError(_("Type a labour charge of 0 or more."))
        visit = self.sudo()
        labour = visit._vr_labour_lines()
        currency = (visit.company_id or self.env.company).currency_id
        visit.labour_set = True
        if currency.compare_amounts(amount, 0.0) <= 0:
            labour.unlink()
            visit.message_post(body=_("Labour only: free."), subtype_xmlid='mail.mt_note')
            return True
        if labour:
            labour[1:].unlink()
            labour = labour[:1]
            labour.unit_price = amount
        else:
            labour = visit._vr_set_price(amount, brand=brand)
        labour.description = name or _("Labour")
        visit.message_post(body=_("Labour only: %(job)s %(cur)s %(amount)s (the customer approves it first).",
                                  job=name or _("charge"), cur=currency.name,
                                  amount='%.*f' % (currency.decimal_places, amount)),
                           subtype_xmlid='mail.mt_note')
        return True

    def _vr_labour_note(self):
        """For the office: 'free', the labour charge, or '' when the outcome is not Labour only
        or the technician has not chosen free / a charge yet."""
        self.ensure_one()
        visit = self.sudo()
        if visit.check_outcome != 'labour' or not visit.labour_set:
            return ''
        charge = sum(l.unit_price * l.quantity for l in visit._vr_labour_lines())
        return charge if charge > 0 else 'free'

    def _vr_need(self):
        """What the parts and the price allow: {parts, in_office (all here), to_order (some to
        order), needs_quote (the price - repairs and parts - is above what the customer
        approved), choices (a part offered in two grades, not chosen yet), approved, total}."""
        lines = [l for l in self._vr_lines() if not l['alt_off']]
        card = self.sudo().job_card_id
        total = card._wb_lines_total() if card else 0.0
        if self.check_outcome == 'labour':
            # Labour only is free unless the customer approved a labour charge: any charge is quoted
            approved = card.estimate_total if card and card.quote_state == 'accepted' else 0.0
        else:
            approved = card.estimate_total if card and card.quote_state in ('none', 'accepted') else 0.0
        currency = (self.company_id or self.env.company).currency_id
        return {
            'parts': len(lines),
            'in_office': bool(lines) and all(l['status'] in ('in_stock', 'other_branch') for l in lines),
            'to_order': any(l['status'] == 'order' for l in lines),
            'needs_quote': currency.compare_amounts(total, approved) > 0,
            'choices': bool(card and card._wb_alt_groups()),
            'approved': approved,
            'total': total,
        }

    # ------------------------------------------------------------------ the outcomes
    def _vr_require(self):
        self.ensure_one()
        self._fs_require(('in_progress',))

    def _vr_note(self, note):
        if note is not None:
            self.sudo().check_found = (note or '').strip()[:2000] or False
        card = self.sudo().job_card_id
        if card and self.check_found and 'inspection_notes' in card._fields:
            card.inspection_notes = self.check_found

    def _vr_set(self, result, **vals):
        vals.update(check_result=result, check_result_on=fields.Datetime.now())
        self.sudo().write(vals)

    def _vr_clear_plan(self):
        self.sudo().write({'pend_plan': False, 'pend_days': 0, 'pend_within': False,
                           'pend_part_days': 0, 'pend_date': False})

    def _vr_span(self, amount, unit='days'):
        """(days, words) for "2 weeks" / "3 days" - the repair time the technician gives."""
        amount = int(amount or 0)
        if unit == 'weeks':
            if not 1 <= amount <= MAX_DAYS // 7:
                raise UserError(_("How many weeks to fix? Between 1 and %s.", MAX_DAYS // 7))
            return amount * 7, (_("1 week") if amount == 1 else _("%s weeks", amount))
        if not 1 <= amount <= MAX_DAYS:
            raise UserError(_("How many days to fix? Between 1 and %s.", MAX_DAYS))
        return amount, (_("1 day") if amount == 1 else _("%s days", amount))

    def _vr_fixed(self, note=None):
        """Fixed on the spot (or the approved repair is done): the visit is done. Parts that
        raise the price need the customer's OK first."""
        self._vr_require()
        self._vr_note(note)
        need = self._vr_need()
        if self.check_outcome == 'labour' and self.check_result != 'repairing' and not self.sudo().labour_set:
            raise UserError(_("Labour only: choose Free, or the labour charge, first."))
        if self.check_outcome == 'parts' and self.check_result != 'repairing' and not need['parts']:
            raise UserError(_("Needs parts: add the part first. Fixed on the spot is for a part you have "
                              "at the price the customer agreed; otherwise send the quotation."))
        if self.check_result != 'repairing' and (need['needs_quote'] or need['to_order']):
            raise UserError(_("The price changed: send the quotation first, the customer approves "
                              "before the repair."))
        if need['choices']:
            raise UserError(_("A part is offered in two grades: tap the one the customer keeps, or send the "
                              "quotation so they choose."))
        self._vr_clear_plan()
        self._vr_set('fixed')
        self.message_post(body=_("Repair done at the customer's place. %s", self.check_found or ''),
                          subtype_xmlid='mail.mt_note')
        self._vr_after_fixed()
        return True

    def _vr_after_fixed(self):
        """After the repair: the visit closes (visit_closeout adds the payment and the finish first)."""
        self.action_done()

    # --- 1. the quotation, with the plan the technician proposes
    def _vr_send_quote(self, plan, days=None, unit='days', part_days=None, note=None):
        """Quote first, always (as on Urban Company): the parts and the price go to the customer
        with the timeline; nothing is repaired, taken or ordered before their OK."""
        self._vr_require()
        need = self._vr_need()
        if not need['parts'] and not need['needs_quote']:
            raise UserError(_("Nothing to quote: no part, and the price is what the customer agreed. "
                              "Use Fixed on the spot."))
        allowed = ('keep', 'order_take') if need['to_order'] else ('now', 'take', 'come_back')
        if plan not in allowed:
            raise UserError(_("Choose what happens to the device."))
        self._vr_note(note)
        visit = self.sudo()
        card, order = visit.job_card_id, visit.order_id
        if not order:
            raise UserError(_("This visit has no website booking to send the quotation to."))
        today = fields.Date.context_today(self)
        total, within, wait = 0, '', 0
        if plan in ('take', 'come_back', 'order_take'):
            total, within = self._vr_span(days, unit)
        if plan in ('keep', 'order_take'):
            wait = int(part_days or 0)
            if not 1 <= wait <= 120:
                raise UserError(_("When does the part arrive? Give the days (1 to 120)."))
            order.write({'parts_days': wait})          # "about N days" in the ordering messages
        date = fields.Date.add(today, days=wait + total) if total else False
        when = date.strftime('%a %d %b') if date else ''
        timeline = {
            'now': (_("Our technician has the part and fixes it now, once you approve.") if need['parts']
                    else _("Our technician fixes it now, once you approve.")),
            'take': _("We take your device to our office: fixed within %(within)s, back by %(date)s.",
                      within=within, date=when),
            'come_back': _("We have the part: fixed within %(within)s, by %(date)s - we come back to you.",
                           within=within, date=when),
            'keep': _("The part must be ordered (about %s days). We tell you when it arrives.", wait),
            'order_take': _("The part must be ordered (about %(wait)s days); we keep your device at our office "
                            "and bring it back repaired by %(date)s.", wait=wait, date=when),
        }[plan]
        found = ', '.join(card.issue_type_ids.mapped('name'))
        if found:
            timeline = _("We found: %s.", found) + '\n' + timeline
        visit.write({'pend_plan': plan, 'pend_days': total, 'pend_within': within or False,
                     'pend_part_days': wait, 'pend_date': date})
        self._vr_set('waiting', check_days=wait + total)
        card._wb_send_new_price(timeline=timeline)
        visit.message_post(body=_("Quotation sent, waiting for the customer's OK. %s", timeline),
                           subtype_xmlid='mail.mt_note')
        return True

    # --- "Can it be fixed?"
    def _vr_outcome(self, outcome, note=None, days=None, unit='days', brand=None, fee=False, waive=False):
        """The technician's first answer. Needs parts / labour only: the parts and the price
        follow on the same screen. Lab check: the device goes to the office (accessories next),
        the price follows from there. No fault / not worth it / brand warranty: the visit closes
        with the reason, which the customer gets on WhatsApp. No fault with `fee`: the visit fee
        is paid at the door first (visit_closeout `_vr_no_fault_fee`)."""
        self._vr_require()
        if outcome not in dict(OUTCOMES):
            raise UserError(_("Choose what you found."))
        self._vr_note(note)
        visit = self.sudo()
        if outcome in ('parts', 'labour'):
            was = visit.check_outcome
            visit.check_outcome = outcome
            if outcome == 'labour' and was != 'labour':
                visit._vr_labour_free(brand=brand)
            elif outcome == 'parts' and was == 'labour':
                visit._vr_labour_restore()
            return True
        if outcome == 'lab':
            card = visit._vr_card(brand=brand)
            total, within = visit._vr_span(days, unit)
            date = fields.Date.add(fields.Date.context_today(self), days=total)
            visit.write({'check_outcome': 'lab', 'pend_plan': 'take', 'pend_days': total, 'pend_within': within,
                         'pend_part_days': 0, 'pend_date': date})
            order = visit.order_id
            if not order or card.wb_lab_ok:
                # no website customer to ask, or they already agreed (a pickup visit): take it
                visit._vr_set('to_take', check_days=total)
                visit.message_post(body=_("Needs a lab check: the device goes to the office, the price follows "
                                          "within %s.", within), subtype_xmlid='mail.mt_note')
                return True
            # the customer's OK first: nothing leaves their place without it (WhatsApp, My orders or at the door)
            card.quote_state = 'waiting'
            visit._vr_set('waiting', check_days=total)
            link = order._wb_new_slot_link().replace('/slot?', '/quote?')
            order._wb_notify('lab_permission', device=card._fix_device_name(), days=within,
                             date=date.strftime('%a %d %b'), quote_url=link)
            visit.message_post(body=_("Needs a lab check (price within %s): asked the customer's OK to take the device.",
                                      within), subtype_xmlid='mail.mt_note')
            return True
        if not (visit.check_found or '').strip():
            raise UserError(_("Write what you checked and why it is not repaired: the customer reads it."))
        # the office's switch (Repair Settings): the visit fee on every "No fault found" and "Not worth
        # repairing", a re-check free. Not worth repairing: the technician may waive it at the door.
        due = fee or visit._vr_fee_view()
        if due and outcome == 'not_worth' and waive:
            visit.message_post(body=_("Visit fee waived by %s (not worth repairing).", self.env.user.name),
                               subtype_xmlid='mail.mt_note')
            due = False
        if outcome in FEE_OUTCOMES and due:
            return visit._vr_no_fault_fee(brand=brand, outcome=outcome)
        return visit._vr_no_repair(outcome)

    # --- no fault found: free, or the visit fee; a free re-check when the problem comes back
    def _vr_visit_fee(self):
        """The visit fee product (Repair Settings), or an empty record."""
        return self.env['job.card'].sudo()._visit_fee_product()

    def _vr_recheck_of(self):
        """This customer's last "No fault found" visit within the free re-check days, or an empty
        record: the problem came back, so this check is free."""
        self.ensure_one()
        visit = self.sudo()
        days = (visit.company_id or self.env.company).fix_recheck_days
        if not days or days <= 0 or not (visit.partner_id or visit.phone):
            return self.browse()
        who = [('partner_id', '=', visit.partner_id.id)] if visit.partner_id else []
        if visit.phone:
            who = (['|'] + who if who else []) + [('phone', '=', visit.phone)]
        since = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        return self.sudo().search([('id', '!=', visit.id), ('check_outcome', '=', 'no_fault'),
                                   ('check_result_on', '>=', since)] + who,
                                  order='check_result_on desc', limit=1)

    def _vr_recheck_line(self):
        """The customer's free re-check line ('' when the company gives none)."""
        days = (self.company_id or self.env.company).fix_recheck_days
        if not days or days <= 0:
            return ''
        return _("If the problem comes back within %s days, book again: the check is free.", days)

    def _vr_no_repair(self, outcome):
        """Not repaired (no fault / not worth it / brand warranty): the job card is closed as not
        done, the booking is done, the customer gets the reason."""
        self.ensure_one()
        visit = self.sudo()
        card, order = visit.job_card_id, visit.order_id
        reason = dict(OUTCOMES)[outcome]
        if card:
            if card.spare_request_ids.filtered(lambda r: r.state == 'issued'):
                raise UserError(_("Parts were issued for %s: give them back to the office first.", card.name))
            # quietly: the customer gets the reason below, not the plain "cancelled" message
            card.with_context(wb_silent=True).write({'state': 'cancelled'})
            card.message_post(body=_("Not repaired at the visit: %(reason)s. %(found)s",
                                     reason=_(reason), found=visit.check_found or ''))
        visit.check_outcome = outcome
        visit._vr_clear_plan()
        visit._vr_set('no_repair')
        visit.action_done()
        if order and order.state not in ('done', 'cancelled'):
            order._set_state('done')
        visit.with_context(osm_extra={'reason': '%s. %s' % (_(reason), visit.check_found or ''),
                                      'recheck': visit._vr_recheck_line() if outcome == 'no_fault' else ''}) \
            ._fs_notify('visit_no_repair')
        visit.message_post(body=_("Not repaired: %(reason)s. %(found)s", reason=_(reason), found=visit.check_found or ''),
                           subtype_xmlid='mail.mt_note')
        return True

    # --- a part that is not in the list: the office finds it and prices it
    def _vr_request_part(self, name, price=None, data=None, brand=None, note=None):
        """The office is asked for a part the list does not have (a purchase request with the
        technician's rough price and photo). The visit closes; the customer hears the price
        follows. The office adds the part to the job card and presses "Send new price"."""
        self._vr_require()
        self._vr_note(note)
        if self.ask_state == 'asked' and not (name or '').strip():
            # "Don't wait" from the question already sent: the office sources that part
            name, price, data = self.ask_name, price if price is not None else self.ask_price, data or self.sudo().ask_photo
        name = (name or '').strip()[:120]
        if len(name) < 2:
            raise UserError(_("Type the part's name."))
        try:
            price = max(float(price or 0.0), 0.0)
        except (TypeError, ValueError):
            price = 0.0
        raw = b''
        if data:
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, TypeError):
                raise UserError(_("The photo could not be read."))
            if _sniff(raw) != 'image' or len(raw) > PHOTO_BYTES:
                raise UserError(_("That is not a photo (or it is too large)."))
        visit = self.sudo()
        card = visit._vr_card(brand=brand)
        # mobile_repair links a part order to its job card through a spare request
        # (as booking/_wb_order_parts and the job card's own button do)
        holder = self.env['spare.part.request'].sudo().create({'job_card_id': card.id})
        request = self.env['spare.part.purchase.request'].sudo().create({
            'spare_request_id': holder.id,
            'product_name': name,
            'product_description': _("For %(card)s (visit %(visit)s)", card=card.name, visit=visit.name),
            'estimated_cost': price,
            'quantity': 1.0,
            'urgency': 'high',
            'company_id': card.company_id.id,
            'notes': _("Asked by %(tech)s at visit %(visit)s: no matching part in the list. %(found)s",
                       tech=visit.technician_id.name or self.env.user.name, visit=visit.name,
                       found=visit.check_found or ''),
        })
        request.action_request()
        if raw:
            self.env['ir.attachment'].sudo().create({
                'name': '%s.jpg' % name[:60], 'datas': base64.b64encode(raw),
                'res_model': request._name, 'res_id': request.id})
        order = visit.order_id
        card.activity_schedule('mail.mail_activity_data_todo',
                               summary=_("Find and price the part: %s", name),
                               note=_("Rough price from the technician: %s. Add the part to the job card, then "
                                      "press \"Send new price\".", price),
                               user_id=(order.approved_by_id or self.env.user).id if order else self.env.user.id)
        visit.check_outcome = 'parts'
        visit._vr_clear_plan()
        # kept in the part questions: the open one ("Don't wait") or a new line for this one
        later = _("The office finds it later: purchase request %s.", request.name)
        if visit.ask_state == 'asked':
            visit._vr_ask_row()._answer('later', reply=later)
        else:
            self.env['fix.part.ask'].sudo().create({
                'visit_id': visit.id, 'job_card_id': card.id, 'technician_id': visit.technician_id.id,
                'name': name, 'rough_price': price, 'photo': base64.b64encode(raw) if raw else False,
                'state': 'later', 'reply': later})
        visit._vr_ask_clear()
        visit._vr_set('sourcing')
        visit.action_done()
        visit.with_context(osm_extra={'part': name})._fs_notify('visit_part_sourcing')
        visit.message_post(body=_("Part asked of the office (%(req)s): %(name)s, about %(price)s.",
                                  req=request.name, name=name, price=price), subtype_xmlid='mail.mt_note')
        return request

    # --- the same question, while the technician waits at the door: the office answers on the desk
    def _vr_ask_office(self, name, price=None, data=None, brand=None, note=None):
        """Ask the office for a part the list does not have, and wait: the Booking Desk rings and
        shows "Part asked"; the office adds the part to the job card (or says it is not available)
        and the technician's screen shows the answer. The visit stays open."""
        self._vr_require()
        self._vr_note(note)
        name = (name or '').strip()[:120]
        if len(name) < 2:
            raise UserError(_("Type the part's name."))
        try:
            price = max(float(price or 0.0), 0.0)
        except (TypeError, ValueError):
            price = 0.0
        photo = False
        if data:
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, TypeError):
                raise UserError(_("The photo could not be read."))
            if _sniff(raw) != 'image' or len(raw) > PHOTO_BYTES:
                raise UserError(_("That is not a photo (or it is too large)."))
            photo = base64.b64encode(raw)
        visit = self.sudo()
        card = visit._vr_card(brand=brand)
        if visit.ask_state == 'asked':
            visit._vr_ask_row()._answer('cancelled')    # a new question replaces one still open
        now = fields.Datetime.now()
        row = self.env['fix.part.ask'].sudo().create({
            'visit_id': visit.id, 'job_card_id': card.id, 'technician_id': visit.technician_id.id,
            'name': name, 'rough_price': price, 'photo': photo, 'asked_on': now})
        visit.write({'ask_state': 'asked', 'ask_name': name, 'ask_price': price, 'ask_photo': photo,
                     'ask_on': now, 'ask_reply': False, 'ask_product_id': False,
                     'ask_replied_by_id': False, 'ask_replied_on': False, 'ask_id': row.id})
        visit.message_post(body=_("%(tech)s asks the office for a part: %(name)s (about %(price)s). Waiting at the door.",
                                  tech=visit.technician_id.name or self.env.user.name, name=name, price=price),
                           subtype_xmlid='mail.mt_note')
        if visit.order_id:
            visit.order_id._ring()          # the Booking Desk rings and shows "Part asked"
        return True

    def _vr_ask_require(self):
        self.ensure_one()
        if self.state != 'in_progress' or self.ask_state != 'asked':
            raise UserError(_("No part is waiting for the office's answer on %s.", self.name))

    def _vr_ask_found(self, product=None, price=None, new_name=None, note=None):
        """The office's answer: this part (from the list, or a new one by its name) at this price,
        added to the job card; the technician carries on from there."""
        self._vr_ask_require()
        visit = self.sudo()
        try:
            price = round(float(price), 6) if price not in (None, '', False) else None
        except (TypeError, ValueError):
            raise UserError(_("Type the price."))
        if price is not None and not 0 <= price <= MAX_PRICE:
            raise UserError(_("Type a price of 0 or more."))
        if not product:
            new_name = (new_name or '').strip()[:120]
            if len(new_name) < 2:
                raise UserError(_("Choose the part, or type the new part's name."))
            if price is None:
                raise UserError(_("Type the price of the new part."))
            category, brand, model = visit._vr_device()
            product = self.env['product.product'].sudo().create({
                'name': new_name, 'type': 'consu', 'is_storable': True, 'sale_ok': True, 'lst_price': price,
                'fit_category_ids': [(6, 0, category.ids)] if category else False})
        line = visit._vr_add_part(product)
        if price is not None:
            line.unit_price = price
        reply = (note or '').strip()[:500]
        row = visit._vr_ask_row()               # while the question still counts as open
        visit.write({'ask_state': 'found', 'ask_product_id': product.id, 'ask_reply': reply or False,
                     'ask_replied_by_id': self.env.uid, 'ask_replied_on': fields.Datetime.now()})
        row._answer('found', product_id=product.id, price=line.unit_price, reply=reply or False)
        visit.message_post(body=_("Office (%(who)s) added %(part)s at %(price)s for the technician. %(note)s",
                                  who=self.env.user.name, part=product.display_name, price=line.unit_price,
                                  note=reply), subtype_xmlid='mail.mt_note')
        if visit.order_id:
            visit.order_id._ring()
        return line

    def _vr_ask_none(self, reason):
        """The office's answer: not available, and why; the technician chooses what next."""
        self._vr_ask_require()
        reason = (reason or '').strip()[:500]
        if not reason:
            raise UserError(_("Write why the part is not available: the technician reads it."))
        visit = self.sudo()
        row = visit._vr_ask_row()               # while the question still counts as open
        visit.write({'ask_state': 'none', 'ask_reply': reason, 'ask_replied_by_id': self.env.uid,
                     'ask_replied_on': fields.Datetime.now()})
        row._answer('none', reply=reason)
        visit.message_post(body=_("Office (%(who)s): %(part)s is not available. %(reason)s",
                                  who=self.env.user.name, part=visit.ask_name, reason=reason),
                           subtype_xmlid='mail.mt_note')
        if visit.order_id:
            visit.order_id._ring()
        return True

    def _vr_ask_cancel(self):
        """The technician takes the question back (asked by mistake, or found the part after all)."""
        self.ensure_one()
        if self.ask_state:
            self.sudo().message_post(body=_("Question to the office taken back: %s.", self.ask_name or ''),
                                     subtype_xmlid='mail.mt_note')
        self._vr_ask_row()._answer('cancelled')
        self._vr_ask_clear()
        if self.order_id:
            self.sudo().order_id._ring()
        return True

    def _vr_ask_clear(self):
        self.sudo().write({'ask_state': False, 'ask_name': False, 'ask_price': 0.0, 'ask_photo': False,
                           'ask_on': False, 'ask_reply': False, 'ask_product_id': False,
                           'ask_replied_by_id': False, 'ask_replied_on': False, 'ask_id': False})

    def _vr_ask_row(self):
        """The history line of the visit's question; for one asked before the history was kept,
        made from the visit's own fields - still waiting, or with the answer it already got."""
        self.ensure_one()
        visit = self.sudo()
        if visit.ask_id or not visit.ask_state:
            return visit.ask_id
        vals = {
            'visit_id': visit.id, 'job_card_id': visit.job_card_id.id, 'technician_id': visit.technician_id.id,
            'name': visit.ask_name or _("Part"), 'rough_price': visit.ask_price, 'photo': visit.ask_photo,
            'asked_on': visit.ask_on or fields.Datetime.now(), 'state': visit.ask_state,
        }
        if visit.ask_state != 'asked':
            line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.product_id == visit.ask_product_id)[:1]
            vals.update(reply=visit.ask_reply or False, product_id=visit.ask_product_id.id,
                        price=line.unit_price if line else 0.0, answered_by_id=visit.ask_replied_by_id.id,
                        answered_on=visit.ask_replied_on)
        row = self.env['fix.part.ask'].sudo().create(vals)
        visit.ask_id = row
        return row

    @api.model
    def _vr_ask_backfill(self, visits):
        """Questions asked before the history was kept get their line when a screen shows them."""
        for visit in visits.sudo().filtered(lambda v: v.ask_state and not v.ask_id):
            visit._vr_ask_row()

    def _vr_ask_history(self):
        """Every part question of this booking's visits (newest first), for the screens."""
        self.ensure_one()
        visit = self.sudo()
        self._vr_ask_backfill(visit.order_id.visit_ids or visit)
        holder = [('order_id', '=', visit.order_id.id)] if visit.order_id else [('visit_id', '=', visit.id)]
        return [a._row() for a in self.env['fix.part.ask'].sudo().search(holder, limit=50)]

    def _vr_ask_view(self):
        """The question and its answer, for the technician's screens and the desk."""
        self.ensure_one()
        visit = self.sudo()
        if not visit.ask_state:
            return None
        line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.product_id == visit.ask_product_id)[:1]
        return {
            'state': visit.ask_state,
            'name': visit.ask_name or '',
            'price': visit.ask_price or 0.0,
            # its file only (reading the field would load the photo on every refresh)
            'photo': bool(self.env['ir.attachment'].sudo().search_count(
                [('res_model', '=', visit._name), ('res_id', '=', visit.id), ('res_field', '=', 'ask_photo')])),
            'on': fields.Datetime.to_string(visit.ask_on) if visit.ask_on else '',
            'reply': visit.ask_reply or '',
            'part': visit.ask_product_id.display_name or '',
            'part_price': line.unit_price if line else 0.0,
            'by': visit.ask_replied_by_id.name or '',
        }

    # --- 2. the customer's answer
    def _vr_approved_here(self):
        """The customer said yes to the technician at the door."""
        self._vr_require()
        card = self.sudo().job_card_id
        if self.check_result != 'waiting' or not card:
            raise UserError(_("There is no quotation waiting for the customer."))
        card._wb_quote_approved(by=_("%s, at the customer's door", self.env.user.name))   # -> _vr_approved
        return True

    def _vr_declined_here(self):
        self._vr_require()
        card = self.sudo().job_card_id
        if self.check_result != 'waiting' or not card:
            raise UserError(_("There is no quotation waiting for the customer."))
        card.quote_state = 'declined'
        card.message_post(body=_("Customer declined the price at the door (noted by %s).", self.env.user.name))
        self._vr_declined()
        return True

    def _vr_decide_later(self):
        """No answer while the technician is there: the visit closes, the quotation stays open."""
        self._vr_require()
        if self.check_result != 'waiting':
            raise UserError(_("There is no quotation waiting for the customer."))
        self._vr_set('quoted')
        self.action_done()
        self.message_post(body=_("The customer will answer the quotation later; the visit is closed."),
                          subtype_xmlid='mail.mt_note')
        return True

    def _vr_approved(self):
        """The customer approved (link, phone or at the door): the plan goes ahead. Ordering
        the missing part is done by the quotation itself (booking/: _wb_quote_approved)."""
        for visit in self.sudo().filtered('pend_plan'):
            plan, here = visit.pend_plan, visit.state == 'in_progress'
            order = visit.order_id
            if visit.check_outcome == 'lab':
                # the customer agreed to the lab check: take it now, or come back to collect it
                if visit.job_card_id:
                    # the OK to take it is not a price: the office sends the price after the check
                    visit.job_card_id.write({'wb_lab_ok': True, 'quote_state': 'none'})
                if here:
                    visit._vr_set('to_take')
                    visit.message_post(body=_("Customer agreed: take the device to the lab (record the accessories)."),
                                       subtype_xmlid='mail.mt_note')
                    continue
                order.write({'parts_state': 'ready', 'slot_id': False, 'slot_date': False,
                             'slot_booked_on': False, 'slot_seen_by_id': False})
                link = order._wb_new_slot_link()
                order._wb_notify('lab_pickup', device=visit.job_card_id._fix_device_name(), slot_url=link)
                visit._vr_set('come_back')
                visit._vr_clear_plan()
                continue
            if plan == 'now' and here:
                visit._vr_set('repairing')
                visit.message_post(body=_("Customer approved: the technician repairs it now."),
                                   subtype_xmlid='mail.mt_note')
                continue
            if plan in ('take', 'order_take') and here:
                visit._vr_set('to_take')
                visit.message_post(body=_("Customer approved: take the device to the office (record the accessories)."),
                                   subtype_xmlid='mail.mt_note')
                continue
            if plan in ('keep', 'order_take'):
                visit._vr_set('ordered')
                if visit.job_card_id and visit.pend_date:
                    visit.job_card_id.wb_return_by = visit.pend_date
                visit._vr_clear_plan()
                if visit.state == 'in_progress':
                    visit.action_done()
                continue
            # 'come_back', or a "now" / "take" approved after the technician left: we come back
            days = visit.pend_days or 1
            date = fields.Date.add(fields.Date.context_today(visit), days=days)
            order.write({'parts_state': 'ready', 'slot_id': False, 'slot_date': False,
                         'slot_booked_on': False, 'slot_seen_by_id': False})
            link = order._wb_new_slot_link()
            order._wb_notify('part_in_stock', days=days, date=date.strftime('%a %d %b'),
                             within=visit.pend_within or _("%s days", days),
                             device=visit.job_card_id._fix_device_name(),
                             next=_("Pick when we come back: %s", link), slot_url=link)
            if visit.job_card_id:
                visit.job_card_id.wb_return_by = date
            visit._vr_set('come_back')
            visit._vr_clear_plan()
            if visit.state == 'in_progress':
                visit.action_done()
        return True

    def _vr_declined(self):
        """The customer said no: nothing is repaired or ordered; with "Visit fee + quote" only
        the visit fee is billed (repair/)."""
        for visit in self.sudo().filtered(lambda v: v.check_result in ('waiting', 'quoted')):
            lab = visit.check_outcome == 'lab'
            visit._vr_clear_plan()
            visit._vr_set('declined')
            if visit.state == 'in_progress':
                visit.action_done()
            visit.message_post(body=_("Customer didn't want the lab check: the device stays with them, not repaired.")
                               if lab else _("Customer declined the quotation: nothing repaired or ordered."),
                               subtype_xmlid='mail.mt_note')
        return True

    # --- 3. after an approved "take": the device goes to the office
    def _vr_take(self, accessories=None, no_accessories=False):
        """The booking's own office step (accessories, return date, the visit closed); the
        customer hears when it comes back (_vr_after_take)."""
        self._vr_require()
        if self.check_result != 'to_take':
            raise UserError(_("Take the device after the customer approved the quotation."))
        card = self.sudo().job_card_id
        wizard = self.env['wb.office.wizard'].with_context(wb_office_silent=True, fix_visit_take=self.id).create({
            'job_card_id': card.id, 'return_by': self.pend_date or fields.Date.context_today(self),
            # "device only" means nothing else was taken, whatever was ticked before
            'accessory_ids': [(6, 0, accessories.ids if accessories and not no_accessories else [])],
            'no_accessories': no_accessories,
        })
        wizard.action_confirm()
        return True

    def action_open_take(self):
        """The office step from a form or the desk, for an approved "take"."""
        self.ensure_one()
        if self.check_result != 'to_take':
            raise UserError(_("Take the device after the customer approved the quotation."))
        return {
            'type': 'ir.actions.act_window', 'name': _("Take %s to the office", self.job_card_id.name),
            'res_model': 'wb.office.wizard', 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
            'context': {'default_job_card_id': self.job_card_id.id, 'default_return_by': self.pend_date,
                        'wb_office_silent': True, 'fix_visit_take': self.id},
        }

    def _vr_after_take(self, return_by):
        """Called by the office step: tell the customer when the device comes back."""
        for visit in self.sudo():
            order, card = visit.order_id, visit.job_card_id
            date = return_by.strftime('%a %d %b') if return_by else ''
            # the customer's receipt: what was taken with the device (booking/office_device.py)
            accessories = card._wb_accessories_text() if hasattr(card, '_wb_accessories_text') else ''
            if visit.check_outcome == 'lab':
                # no price yet: the lab checks it, the office sends the quotation by the promised date
                if 'wb_price_by' in card._fields:
                    card.wb_price_by = return_by
                visit.with_context(osm_extra={'days': visit.pend_within or _("%s days", visit.pend_days),
                                              'date': date, 'device': card._fix_device_name(),
                                              'accessories': accessories}
                                   )._fs_notify('visit_lab_check')
                visit._vr_set('lab')
                visit._vr_clear_plan()
                continue
            if visit.pend_plan == 'order_take':
                order._wb_notify('office_part_wait', part_days=visit.pend_part_days, within=visit.pend_within or '',
                                 date=date, device=card._fix_device_name(), accessories=accessories,
                                 technician=visit.technician_id.name or '')
            else:
                order._wb_notify('part_in_stock', days=visit.pend_days, within=visit.pend_within or '', date=date,
                                 device=card._fix_device_name(), slot_url='',
                                 next=_("Your device is with us and will come back repaired."))
            visit._vr_set('office')
            visit._vr_clear_plan()

    # ------------------------------------------------------------------ Odoo window
    def action_vr_approved_here(self):
        return self._vr_approved_here()

    def action_vr_declined_here(self):
        return self._vr_declined_here()

    def action_vr_later(self):
        return self._vr_decide_later()

    def action_vr_done(self):
        return self._vr_fixed()

    def action_open_part_ask(self):
        """The office's answer to the technician's part question (Booking Desk: "Part found")."""
        self.ensure_one()
        self._vr_ask_require()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Part for %s", self.name),
            'res_model': 'fix.part.ask.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_visit_id': self.id},
        }

    def action_open_result(self):
        self.ensure_one()
        self._vr_require()
        return {
            'type': 'ir.actions.act_window',
            'name': _("What did you find? - %s", self.name),
            'res_model': 'fix.visit.result.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_visit_id': self.id},
        }

    # ------------------------------------------------------------------ the phone page
    def _vr_view(self):
        self.ensure_one()
        visit = self.sudo()
        need = visit._vr_need()
        currency = (visit.company_id or self.env.company).currency_id
        view = {
            'currency': currency.name,
            'decimals': currency.decimal_places,
            'found': visit.check_found or '',
            'stage': visit.check_result if visit.check_result in ('waiting', 'repairing', 'to_take') else 'find',
            'plan_label': (_("Take it to our lab for a check (the customer's OK first)")
                           if visit.check_outcome == 'lab' and visit.check_result == 'waiting'
                           else dict(PLANS).get(visit.pend_plan, '')),
            'timeline_date': visit.pend_date.strftime('%a %d %b') if visit.pend_date else '',
            'need_device': not visit.job_card_id and not visit._vr_device_guess()[1],
            'outcome': visit.check_outcome or '',
            # "Under the brand's warranty" is asked first, in "Before you start" (visit_checks.py)
            'outcomes': [{'key': k, 'label': _(label)} for k, label in OUTCOMES if k != 'warranty'],
            'lines': visit._vr_lines(),
            'services': visit._vr_services(),
            'issues': visit._vr_issues(),
            'suggested': visit._vr_suggest() if visit.check_result not in ('waiting', 'repairing', 'to_take') else [],
            'needs_quote': need['needs_quote'],
            'choices': need['choices'],
            'to_order': need['to_order'],
            'approved': need['approved'],
            'total': need['total'],
            'accessories': [{'id': a.id, 'name': a.name} for a in self.env['device.accessory'].sudo().search([])],
            'max_days': MAX_DAYS,
            'part_days': visit.order_id.parts_days or 7,
            'ask': visit._vr_ask_view(),
            'ask_history': visit._vr_ask_history(),
            # Labour only: 'free' or the charge (the customer approves any charge first)
            'labour': visit._vr_labour_note(),
            # the office's fixed labour prices: one tap instead of typing the charge
            'labour_presets': visit._vr_labour_presets() if visit.check_outcome == 'labour' else [],
            'labour_for': visit._vr_device()[0].name or '' if visit.check_outcome == 'labour' else '',
            # No fault found: free, or the visit fee (paid at the door); none on a free re-check
            'visit_fee': visit._vr_fee_view(),
            'recheck': visit._vr_recheck_view(),
            # "Call the office" while waiting for its answer
            'office_phone': (visit.company_id or self.env.company).phone or '',
        }
        if view['need_device']:
            view['brands'] = [{'id': b.id, 'name': b.name}
                              for b in self.env['device.brand'].sudo().search([], order='name')]
        return view

    def _vr_fee_view(self):
        """The visit fee "No fault found" charges: Repair Settings' switch on, a price set and not a
        free re-check (False: free)."""
        company = self.company_id or self.env.company
        fee = self._vr_visit_fee()
        if not company.fix_no_fault_fee or not fee or fee.lst_price <= 0 or self._vr_recheck_of():
            return False
        return fee.lst_price

    def _vr_recheck_view(self):
        """The earlier "No fault found" visit when this one is a free re-check ('' when not)."""
        earlier = self._vr_recheck_of()
        return earlier.check_result_on.strftime('%a %d %b') if earlier else ''

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
        # the part questions of this booking and the office's answers: shown at every step
        if view.get('ref'):
            view['ask_history'] = self._vr_ask_history()
        if self.state == 'in_progress':
            view['result'] = self._vr_view()
        if self.check_result:
            view['result_label'] = dict(RESULTS)[self.check_result]
        return view

    def _vr_tech_act(self, action, args):
        """One step of "What did you find?" from the phone. Returns extra keys for the view."""
        visit = self.sudo()
        Model = lambda name, key: self.env[name].sudo().browse(int(args.get(key) or 0)).exists()  # noqa: E731
        accessories = self.env['device.accessory'].sudo().browse(
            [int(x) for x in (args.get('accessory_ids') or []) if str(x).isdigit()]).exists()
        note = args.get('note')
        if action == 'result_parts':
            return {'parts': visit._vr_parts(args.get('query') or '')}
        if action == 'result_note':
            visit._vr_note(note)
        elif action == 'result_issue':
            issue = Model('job.card.issue.type', 'issue_id')
            if not issue:
                raise UserError(_("Choose a problem."))
            visit._vr_set_issue(issue, bool(args.get('on')), brand=Model('device.brand', 'brand_id'))
        elif action == 'result_add_part':
            product = Model('product.product', 'product_id')
            if not product:
                raise UserError(_("Choose a part."))
            alt_of = None
            if args.get('line_id'):
                alt_of = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.id == int(args['line_id']))
                if not alt_of:
                    raise UserError(_("That part is not on the job card."))
            visit._vr_add_part(product, float(args.get('qty') or 1), brand=Model('device.brand', 'brand_id'),
                               alt_of=alt_of)
        elif action == 'result_remove_part':
            line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.id == int(args.get('line_id') or 0))
            if line:
                visit._vr_remove_part(line)
        elif action == 'result_alts':
            line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.id == int(args.get('line_id') or 0))
            if not line:
                raise UserError(_("That part is not on the job card."))
            return {'alts': visit._vr_alternatives(line), 'alt_of': line.id}
        elif action == 'result_choose':
            line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.id == int(args.get('line_id') or 0))
            if not line:
                raise UserError(_("That part is not on the job card."))
            visit._vr_choose(line)
        elif action == 'result_price':
            visit._vr_set_price(args.get('price'), line_id=args.get('line_id') or 0,
                                product_id=args.get('product_id') or 0, brand=Model('device.brand', 'brand_id'))
        elif action == 'result_outcome':
            visit._vr_outcome(args.get('outcome'), note=note, days=args.get('days'), unit=_unit(args.get('unit')),
                              brand=Model('device.brand', 'brand_id'), fee=bool(args.get('fee')),
                              waive=bool(args.get('waive')))
        elif action == 'result_request':
            visit._vr_request_part(args.get('name'), price=args.get('price'), data=args.get('data'),
                                   brand=Model('device.brand', 'brand_id'), note=note)
        elif action == 'result_labour':
            if args.get('preset_id'):      # a fixed price: never the phone's number
                visit._vr_labour_preset(args['preset_id'], brand=Model('device.brand', 'brand_id'))
            else:
                visit._vr_labour_charge(args.get('price'), brand=Model('device.brand', 'brand_id'))
        elif action == 'result_ask':
            visit._vr_ask_office(args.get('name'), price=args.get('price'), data=args.get('data'),
                                 brand=Model('device.brand', 'brand_id'), note=note)
        elif action == 'result_ask_cancel':
            visit._vr_ask_cancel()
        elif action == 'result_fixed':
            visit._vr_fixed(note)
        elif action == 'result_quote':
            visit._vr_send_quote(args.get('plan'), days=args.get('days'), unit=_unit(args.get('unit')),
                                 part_days=args.get('part_days'), note=note)
        elif action == 'result_approved_here':
            visit._vr_approved_here()
        elif action == 'result_declined_here':
            visit._vr_declined_here()
        elif action == 'result_later':
            visit._vr_decide_later()
        elif action == 'result_take':
            visit._vr_take(accessories, bool(args.get('no_accessories')))
        else:
            raise UserError(_("Unknown action."))
        return {}

    def _fs_tech_do(self, action='', **args):
        """Adds "What did you find?" (the result_* steps) to the technician's steps."""
        if not action.startswith('result_'):
            return super()._fs_tech_do(action, **args)
        visit = self.sudo()
        if visit.state != 'in_progress':
            return dict(visit._fs_tech_view(), ok=False, error='state',
                        message=_("This is done while the work is in progress."))
        if action == 'result_parts':
            # searched as the technician types: the parts only, not the whole page each time
            return {'ok': True, 'parts': visit._vr_parts(args.get('query') or '')}
        try:
            with self.env.cr.savepoint():
                extra = visit._vr_tech_act(action, args)
        except UserError as err:
            return dict(visit._fs_tech_view(), ok=False, error='result', message=str(err))
        return dict(visit._fs_tech_view(), **extra)


class JobCard(models.Model):
    _inherit = 'job.card'

    def _fix_device_name(self):
        self.ensure_one()
        return ' '.join(x for x in (self.brand_id.name, self.model_id.name) if x) or _("device")
