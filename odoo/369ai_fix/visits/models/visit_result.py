# -*- coding: utf-8 -*-
"""What the technician found, and the quotation first - as on Urban Company.

While the visit is Working the technician says what they found and, when the repair
needs parts, picks them from the catalogue - each shows whether the office has it,
another branch has it, or it must be ordered.

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
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
]
# What the technician proposes with the quotation
PLANS = [
    ('now', 'Fix now (the technician has the part)'),
    ('take', 'Take the device to the office'),
    ('come_back', 'Customer keeps it, we come back'),
    ('keep', 'Customer keeps it until the part arrives'),
    ('order_take', 'Take the device to the office until the part arrives'),
]
MAX_DAYS = 60


def _unit(value):
    return 'weeks' if value == 'weeks' else 'days'


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    check_result = fields.Selection(RESULTS, 'Result', readonly=True, copy=False, tracking=True)
    check_found = fields.Text('What the technician found', copy=False)
    check_days = fields.Integer('Fixed within (days)', readonly=True, copy=False)
    check_result_on = fields.Datetime('Result on', readonly=True, copy=False)
    # the plan sent with the quotation, carried out once the customer approves
    pend_plan = fields.Selection(PLANS, 'Proposed', readonly=True, copy=False)
    pend_days = fields.Integer(readonly=True, copy=False)
    pend_within = fields.Char(readonly=True, copy=False)
    pend_part_days = fields.Integer(readonly=True, copy=False)
    pend_date = fields.Date('Back by', readonly=True, copy=False)

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

    def _vr_parts(self, query='', limit=20):
        """Spare parts for the search box: the device's own first, each with its stock."""
        self.ensure_one()
        query = (query or '').strip()
        domain = [('type', '=', 'consu'), ('sale_ok', '=', True)]
        if query:
            domain += ['|', '|', ('name', 'ilike', query), ('default_code', 'ilike', query),
                       ('barcode', '=', query)]
        Product = self.env['product.product'].sudo()
        products = Product.search(domain, limit=200)
        card = self.sudo().job_card_id
        brand, model = (card.brand_id, card.model_id) if card else self._vr_device_guess()[1::2]

        def rank(p):
            return (0 if model and p.device_model_id == model else 1 if brand and p.device_brand_id == brand
                    else 2, 0 if p.is_mobile_repair_part else 1, p.name or '')
        return [self._vr_part_row(p) for p in sorted(products, key=rank)[:limit]]

    def _vr_part_row(self, product, qty=1.0):
        stock = self._vr_stock(product, qty)
        return {'product_id': product.id, 'name': product.display_name, 'price': product.lst_price,
                'office': stock['office'], 'other': stock['other'], 'status': stock['status'],
                'branches': stock['branches']}

    def _vr_lines(self):
        """The parts on the job card, each with where it is."""
        self.ensure_one()
        card = self.sudo().job_card_id
        rows = []
        for line in card.spare_part_line_ids if card else []:
            row = self._vr_part_row(line.product_id, line.quantity)
            row.update(line_id=line.id, qty=line.quantity, name=line.description or line.product_id.display_name)
            rows.append(row)
        return rows

    def _vr_add_part(self, product, qty=1.0, brand=None, model=None, category=None):
        self.ensure_one()
        card = self._vr_card(brand=brand, model=model, category=category)
        line = card.spare_part_line_ids.filtered(lambda l: l.product_id == product)[:1]
        if line:
            line.quantity = qty or line.quantity
        else:
            self.env['job.card.spare.part.line'].sudo().create({
                'job_card_id': card.id, 'product_id': product.id, 'description': product.name,
                'quantity': qty or 1.0, 'unit_price': product.lst_price,
                'tax_ids': [(6, 0, product.taxes_id.filtered(lambda t: t.company_id == card.company_id).ids)],
            })

    def _vr_need(self):
        """What the parts allow: {parts, in_office (all here), to_order (some to order),
        needs_quote (the price is above what the customer approved), total}."""
        lines = self._vr_lines()
        card = self.sudo().job_card_id
        total = card._wb_lines_total() if card else 0.0
        approved = card.estimate_total if card and card.quote_state in ('none', 'accepted') else 0.0
        currency = (self.company_id or self.env.company).currency_id
        return {
            'parts': len(lines),
            'in_office': bool(lines) and all(l['status'] in ('in_stock', 'other_branch') for l in lines),
            'to_order': any(l['status'] == 'order' for l in lines),
            'needs_quote': bool(lines) and currency.compare_amounts(total, approved) > 0,
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
        if self.check_result != 'repairing' and (need['needs_quote'] or need['to_order']):
            raise UserError(_("These parts change the price: send the quotation first, the customer approves "
                              "before the repair."))
        self._vr_clear_plan()
        self._vr_set('fixed')
        self.action_done()
        self.message_post(body=_("Repair done at the customer's place. %s", self.check_found or ''),
                          subtype_xmlid='mail.mt_note')
        return True

    # --- 1. the quotation, with the plan the technician proposes
    def _vr_send_quote(self, plan, days=None, unit='days', part_days=None, note=None):
        """Quote first, always (as on Urban Company): the parts and the price go to the customer
        with the timeline; nothing is repaired, taken or ordered before their OK."""
        self._vr_require()
        need = self._vr_need()
        if not need['parts']:
            raise UserError(_("Add the parts first. No part needed? Use Fixed on the spot."))
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
            'now': _("Our technician has the part and fixes it now, once you approve."),
            'take': _("We take your device to our office: fixed within %(within)s, back by %(date)s.",
                      within=within, date=when),
            'come_back': _("We have the part: fixed within %(within)s, by %(date)s - we come back to you.",
                           within=within, date=when),
            'keep': _("The part must be ordered (about %s days). We tell you when it arrives.", wait),
            'order_take': _("The part must be ordered (about %(wait)s days); we keep your device at our office "
                            "and bring it back repaired by %(date)s.", wait=wait, date=when),
        }[plan]
        visit.write({'pend_plan': plan, 'pend_days': total, 'pend_within': within or False,
                     'pend_part_days': wait, 'pend_date': date})
        self._vr_set('waiting', check_days=wait + total)
        card._wb_send_new_price(timeline=timeline)
        visit.message_post(body=_("Quotation sent, waiting for the customer's OK. %s", timeline),
                           subtype_xmlid='mail.mt_note')
        return True

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
            visit._vr_clear_plan()
            visit._vr_set('declined')
            if visit.state == 'in_progress':
                visit.action_done()
            visit.message_post(body=_("Customer declined the quotation: nothing repaired or ordered."),
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
            if visit.pend_plan == 'order_take':
                order._wb_notify('office_part_wait', part_days=visit.pend_part_days, within=visit.pend_within or '',
                                 date=date, device=card._fix_device_name())
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
        view = {
            'found': visit.check_found or '',
            'stage': visit.check_result if visit.check_result in ('waiting', 'repairing', 'to_take') else 'find',
            'plan_label': dict(PLANS).get(visit.pend_plan, ''),
            'timeline_date': visit.pend_date.strftime('%a %d %b') if visit.pend_date else '',
            'need_device': not visit.job_card_id and not visit._vr_device_guess()[1],
            'lines': visit._vr_lines(),
            'needs_quote': need['needs_quote'],
            'to_order': need['to_order'],
            'total': need['total'],
            'accessories': [{'id': a.id, 'name': a.name} for a in self.env['device.accessory'].sudo().search([])],
            'max_days': MAX_DAYS,
            'part_days': visit.order_id.parts_days or 7,
        }
        if view['need_device']:
            view['brands'] = [{'id': b.id, 'name': b.name}
                              for b in self.env['device.brand'].sudo().search([], order='name')]
        return view

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
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
        elif action == 'result_add_part':
            product = Model('product.product', 'product_id')
            if not product:
                raise UserError(_("Choose a part."))
            visit._vr_add_part(product, float(args.get('qty') or 1), brand=Model('device.brand', 'brand_id'))
        elif action == 'result_remove_part':
            line = visit.job_card_id.spare_part_line_ids.filtered(lambda l: l.id == int(args.get('line_id') or 0))
            line.unlink()
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

    @api.model
    def tech_page(self, host, ref, token, action='', lat=None, lng=None, accuracy=None,
                  heading=None, speed=None, battery=None, code='', **args):
        if not action.startswith('result_'):
            return super().tech_page(host, ref, token, action=action, lat=lat, lng=lng, accuracy=accuracy,
                                     heading=heading, speed=speed, battery=battery, code=code, **args)
        self.env['online.service.order']._check_website_caller()
        visit, error = self._fs_from_tech_link(host, ref, token)
        if error:
            return {'ok': False, 'error': error}
        if visit.state != 'in_progress':
            return dict(visit._fs_tech_view(), ok=False, error='state',
                        message=_("This is done while the work is in progress."))
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
