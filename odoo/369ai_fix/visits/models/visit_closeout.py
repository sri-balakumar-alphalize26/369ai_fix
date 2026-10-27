# -*- coding: utf-8 -*-
"""After the repair, at the customer's door: the after photo, the payment and the finish code.

"Repair done" / "Fixed on the spot" (visit_result) no longer closes a website visit. It opens
Finish, and the visit stays Working until:

1. a photo of the repaired device is taken (1 to 3),
2. the money is collected: the job card's bill is made the way the office's "Create invoice"
   makes it - an Easy Sale with its VAT when the booking is billed with tax, else an Estimate
   Sale (mobile_repair `_create_easy_sales` / `_create_estimate_sale`) - with the payment line
   the technician chose (Cash / Card / Bank Transfer); confirming it posts the invoice and the
   payment. Nothing to pay (price 0): the technician confirms "no charge" instead,
3. the customer reads out the 4-digit finish code they got on WhatsApp and My orders.

Then the job card is completed (the customer's "completed" message, the booking Done), the
visit is Done, and the customer gets the receipt: what they paid, the warranty date and a link
to rate the visit (1-5 stars, rate.astro on the website). A manager can finish without the code
from the Booking Desk; the reason is logged.
"""
import base64
import hmac
import logging
import secrets
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.image import image_process
from odoo.tools.mimetypes import guess_mimetype

from .service_visit import MAX_CODE_TRIES, _iso
from .visit_checks import PHOTO_BYTES, _sniff

_logger = logging.getLogger(__name__)

MAX_AFTER_PHOTOS = 3
CLOSE_STAGES = [('finish', 'Finishing (photo, payment, code)'), ('closed', 'Finished')]


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    close_stage = fields.Selection(CLOSE_STAGES, 'Finish', readonly=True, copy=False, tracking=True)
    finish_code = fields.Char(
        readonly=True, copy=False, groups='mobile_repair.group_mobile_repair_receptionist',
        help="The customer gets this code on WhatsApp and My orders once the repair is done, and "
             "reads it out to the technician to finish the visit.")
    finish_tries = fields.Integer('Wrong finish codes', readonly=True, copy=False)
    finished_on = fields.Datetime(readonly=True, copy=False)
    finish_skip_reason = fields.Char('Finished without the code because', readonly=True, copy=False)
    after_photo_ids = fields.One2many('fix.visit.check.photo', 'visit_id', string='After repair',
                                      domain=[('kind', '=', 'after')])
    # the bill made at the door: an Easy Sale (with tax) or an Estimate Sale (without), as the
    # booking says (booking/: wb_bill_type)
    pay_sale_id = fields.Many2one('easy.sales', 'Bill', readonly=True, copy=False)
    pay_estimate_id = fields.Many2one('estimate.sale', 'Bill (without tax)', readonly=True, copy=False)
    paid_amount = fields.Float('Paid', digits='Product Price', readonly=True, copy=False)
    paid_method_id = fields.Many2one('easy.sales.payment.method', 'Paid by', readonly=True, copy=False)
    paid_estimate_method_id = fields.Many2one('estimate.sale.payment.method', 'Paid by (without tax)',
                                              readonly=True, copy=False)
    paid_on = fields.Datetime(readonly=True, copy=False)
    paid_by_id = fields.Many2one('res.users', 'Collected by', readonly=True, copy=False)
    paid_free = fields.Boolean('No charge', readonly=True, copy=False)
    warranty_until = fields.Date(readonly=True, copy=False)
    rating = fields.Integer('Stars', readonly=True, copy=False, aggregator='avg')
    rating_note = fields.Text('Customer says', readonly=True, copy=False)
    rated_on = fields.Datetime(readonly=True, copy=False)
    # the rating link (/rate?v=&t=); low-stakes (it only rates once), so the token itself is kept
    rate_token = fields.Char(readonly=True, copy=False, groups='base.group_system')

    # ------------------------------------------------------------------ into Finish
    def _vr_after_fixed(self):
        """Repair done: a website visit goes to Finish (photo, payment, code) instead of closing."""
        with_order = self.filtered(lambda v: v.sudo().order_id)
        super(ServiceVisit, self - with_order)._vr_after_fixed()
        for visit in with_order.sudo():
            visit._co_open_finish('visit_finish_code',
                                  _("Repair done: finishing (after photo, payment, the customer's code)."))

    def _co_open_finish(self, message_key, note, **extra):
        """Into Finish: a new finish code, sent to the customer with `message_key`."""
        visit = self.sudo()
        visit.write({'close_stage': 'finish', 'finish_code': self._fs_new_code(), 'finish_tries': 0})
        visit.with_context(osm_extra=dict(extra, code=visit.finish_code))._fs_notify(message_key)
        visit.message_post(body=note, subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------ no fault found, with the visit fee
    def _vr_no_fault_fee(self, brand=None):
        """No fault found, the visit fee charged (the technician's choice): the job card keeps only
        the visit fee - the booked repairs at 0, no parts - and the visit goes to Finish: the
        customer pays at the door and gives the finish code. A visit without a website booking
        closes; the office bills the fee from the job card."""
        self.ensure_one()
        visit = self.sudo()
        fee = visit._vr_visit_fee()
        if not fee:
            raise UserError(_("No visit fee is set in Repair Settings."))
        if visit._vr_recheck_of():
            raise UserError(_("This is a free re-check: no visit fee this time."))
        card = visit._vr_card(brand=brand)
        if card.spare_request_ids.filtered(lambda r: r.state == 'issued'):
            raise UserError(_("Parts were issued for %s: give them back to the office first.", card.name))
        card.spare_part_line_ids.unlink()
        card.service_line_ids.filtered(self._vr_is_labour_line).unlink()
        card.service_line_ids.write({'unit_price': 0.0})
        card.inspection_type = 'paid'               # _co_due(): the visit fee
        visit.check_outcome = 'no_fault'
        visit._vr_clear_plan()
        visit._vr_set('no_repair')
        currency = visit._co_currency()
        fee_text = _("Visit fee %(cur)s %(amount)s", cur=currency.name,
                     amount='%.*f' % (currency.decimal_places, visit._co_due()))
        card.message_post(body=_("No fault found at the visit: only the visit fee. %s", visit.check_found or ''))
        if not visit.order_id:
            visit.action_done()
            return True
        visit._co_open_finish(
            'visit_no_fault_fee', _("No fault found, %s: finishing (payment, the customer's code).", fee_text),
            reason=visit.check_found or '', fee=fee_text)
        return True

    def _co_no_fault(self):
        return self.sudo().check_outcome == 'no_fault'

    def _co_require(self):
        self.ensure_one()
        self._fs_require(('in_progress',))
        if self.close_stage != 'finish':
            raise UserError(_("This is done after the repair, to finish the visit."))

    # ------------------------------------------------------------------ what is due
    def _co_card(self):
        self.ensure_one()
        card = self.sudo().job_card_id
        if not card:
            raise UserError(_("This visit has no job card to bill."))
        return card

    def _co_with_tax(self):
        """Billed with tax (an Easy Sale) or without (an Estimate Sale): the booking's choice."""
        self.ensure_one()
        card = self.sudo().job_card_id
        return bool(card) and card._wb_with_tax()

    def _co_due(self):
        """What the customer pays: the bill once it is made, else what it will be (repairs + the
        paid inspection, if any, + parts; with the VAT when billed with tax) - the price the
        customer approved, the same sum mobile_repair's bills make."""
        self.ensure_one()
        card = self.sudo().job_card_id
        if not card:
            return 0.0
        if card.easy_sales_id:
            return card.easy_sales_id.amount_total
        if card.estimate_sale_id:
            return card.estimate_sale_id.amount_total
        due = card._wb_lines_total()
        fee = self._co_fee_product()
        if fee:
            taxes = self._co_fee_taxes(fee) if card._wb_with_tax() else None
            currency = self._co_currency()
            due += taxes.compute_all(fee.lst_price, currency, 1.0, product=fee)['total_included'] if taxes else fee.lst_price
        return due

    def _co_fee_taxes(self, product):
        company = self.company_id or self.env.company
        return product.taxes_id.filtered(lambda t: t.company_id == company) or company.account_sale_tax_id

    def _co_fee_product(self):
        """The paid inspection (visit fee) the bill adds, or an empty record."""
        self.ensure_one()
        card = self.sudo().job_card_id
        Product = self.env['product.product'].sudo()
        if not card or card.inspection_type != 'paid':
            return Product
        fee = self.env['ir.config_parameter'].sudo().get_param('mobile_repair.inspection_charge_product_id')
        return Product.browse(int(fee)).exists() if fee and str(fee).isdigit() else Product

    def _co_methods(self):
        """How the customer can pay: the payment methods of this booking's bill (the one the office
        already made, else the one the booking gets)."""
        company = self.company_id or self.env.company
        card = self.sudo().job_card_id
        easy = bool(card.easy_sales_id) if card and (card.easy_sales_id or card.estimate_sale_id) else self._co_with_tax()
        model = 'easy.sales.payment.method' if easy else 'estimate.sale.payment.method'
        return self.env[model].sudo().search(
            [('company_id', 'in', [company.id, False]), ('is_customer_account', '=', False)])

    def _co_currency(self):
        return (self.company_id or self.env.company).currency_id

    def _co_paid_text(self):
        self.ensure_one()
        visit = self.sudo()
        if visit.paid_free or not visit.paid_amount:
            return _("No charge")
        currency = visit._co_currency()
        amount = '%s %s' % (currency.name, '%.*f' % (currency.decimal_places, visit.paid_amount))
        method = visit.paid_method_id or visit.paid_estimate_method_id
        return '%s (%s)' % (amount, method.name) if method else amount

    # ------------------------------------------------------------------ the steps
    def _co_photo(self, data):
        self._co_require()
        visit = self.sudo()
        try:
            raw = base64.b64decode(data or '', validate=True)
        except (ValueError, TypeError):
            raise UserError(_("The file could not be read."))
        if _sniff(raw) != 'image':
            raise UserError(_("That is not a photo."))
        if len(raw) > PHOTO_BYTES:
            raise UserError(_("The photo is too large."))
        if len(visit.after_photo_ids) >= MAX_AFTER_PHOTOS:
            raise UserError(_("At most %s photos. Clear them to take new ones.", MAX_AFTER_PHOTOS))
        self.env['fix.visit.check.photo'].sudo().create(
            {'visit_id': visit.id, 'kind': 'after', 'image': base64.b64encode(raw)})
        return True

    def _co_clear_photos(self):
        self._co_require()
        self.sudo().after_photo_ids.unlink()
        return True

    def _co_pay(self, method_id, amount=None):
        """The money collected at the door: the bill with this payment, confirmed - which posts
        the invoice and the payment. The bill is the booking's: an Easy Sale with its VAT (with
        tax) or an Estimate Sale (without), the two bills of mobile_repair's "Create Invoice".
        If confirming fails (stock, accounts...) the payment is still recorded on the bill and
        the office is asked to confirm it."""
        self._co_require()
        visit = self.sudo()
        if visit.paid_on:
            raise UserError(_("The payment is already recorded."))
        method = visit._co_methods().filtered(lambda m: m.id == int(method_id or 0))
        if not method:
            raise UserError(_("Choose how the customer paid."))
        card = visit._co_card()
        if card._wb_alt_groups():
            raise UserError(_("A part is offered in two grades: choose the one the customer keeps first."))
        due = visit._co_due()
        currency = visit._co_currency()
        if currency.compare_amounts(due, 0.0) <= 0:
            raise UserError(_("Nothing to pay: confirm \"No charge\" instead."))
        try:
            amount = due if amount in (None, '', False) else round(float(amount), currency.decimal_places)
        except (TypeError, ValueError):
            raise UserError(_("Type the amount paid."))
        if currency.compare_amounts(amount, 0.0) <= 0 or currency.compare_amounts(amount, due) > 0:
            raise UserError(_("The amount must be more than 0 and at most %s.", '%.*f' % (currency.decimal_places, due)))
        with_tax = visit._co_with_tax()
        sale = card.easy_sales_id or card.estimate_sale_id
        if sale and sale.state != 'draft':
            raise UserError(_("The office has already billed this job (%s).", sale.name))
        if not sale:
            if card.spare_part_line_ids:
                card._sync_spare_issue_entries()
                if card._check_spare_prices():
                    raise UserError(_("A part on the job card is priced below its cost: the office must fix "
                                      "the price before the bill is made."))
            full = currency.compare_amounts(amount, due) == 0
            if with_tax:
                sale = card.with_company(card.company_id)._create_easy_sales()
                visit._co_tax_easy_sale(sale)
            else:
                sale = card.with_company(card.company_id)._create_estimate_sale()
            if full:
                amount = sale.amount_total      # the bill's own rounding of the same total
        sale.payment_line_ids.unlink()
        sale.write({'quick_payment_method_id': method.id})
        line_model = 'easy.sales.payment.line' if sale._name == 'easy.sales' else 'estimate.sale.payment.line'
        self.env[line_model].sudo().create({'sales_id': sale.id, 'payment_method_id': method.id, 'amount': amount})
        bill = {'pay_sale_id': sale.id, 'paid_method_id': method.id} if sale._name == 'easy.sales' \
            else {'pay_estimate_id': sale.id, 'paid_estimate_method_id': method.id}
        visit.write(dict(bill, paid_amount=amount, paid_on=fields.Datetime.now(), paid_by_id=self.env.uid))
        confirmed = True
        try:
            with self.env.cr.savepoint():
                sale.action_confirm()
        except Exception as err:  # noqa: BLE001 - the money is collected; the office finishes the bill
            confirmed = False
            _logger.exception("Visit %s: confirming bill %s failed", visit.name, sale.name)
            card.activity_schedule('mail.mail_activity_data_todo', summary=_("Confirm the bill %s", sale.name),
                                   note=_("Paid at the door (%(paid)s), but the bill could not be confirmed: %(err)s",
                                          paid=visit._co_paid_text(), err=str(err)[:300]),
                                   user_id=(visit.order_id.approved_by_id or self.env.user).id)
        visit.message_post(body=_("Paid at the door: %(paid)s, collected by %(who)s. Bill %(bill)s%(state)s.",
                                  paid=visit._co_paid_text(), who=self.env.user.name, bill=sale.name,
                                  state='' if confirmed else _(" (the office must confirm it)")),
                           subtype_xmlid='mail.mt_note')
        if currency.compare_amounts(amount, due) < 0:
            card.activity_schedule('mail.mail_activity_data_todo', summary=_("Part payment at the door"),
                                   note=_("%(paid)s of %(due)s collected.", paid=amount, due=due),
                                   user_id=(visit.order_id.approved_by_id or self.env.user).id)
        return True

    def _co_tax_easy_sale(self, sale):
        """mobile_repair's Easy Sale from a job card carries no taxes: put on each line the tax the
        customer's price counted (the part's own, the repairs', else the company's VAT), so the
        bill's total is the price the customer approved."""
        self.ensure_one()
        card = self.sudo().job_card_id
        company = card.company_id or self.env.company
        services, parts = card._wb_billed_lines()
        service_taxes = self.env['account.tax']
        for line in services:
            service_taxes |= card._wb_line_taxes(line)
        fee = self._co_fee_product()
        if fee:
            service_taxes |= self._co_fee_taxes(fee)
        for sline in sale.line_ids:
            if getattr(sline, 'display_type', False):
                continue                # a section or a note
            if sline.is_spare_issued:
                part = parts.filtered(lambda l: l.product_id == sline.product_id)[:1]
                taxes = card._wb_line_taxes(part) if part else company.account_sale_tax_id
            else:
                # the combined "Service Charges" line: the repairs' (and the visit fee's) tax
                taxes = service_taxes[:1] or company.account_sale_tax_id
            sline.tax_ids = [(6, 0, taxes.ids)]

    def _co_free(self):
        """Nothing to pay (e.g. a free fix): the technician confirms it."""
        self._co_require()
        visit = self.sudo()
        if visit.paid_on:
            raise UserError(_("The payment is already recorded."))
        if visit._co_currency().compare_amounts(visit._co_due(), 0.0) > 0:
            raise UserError(_("There is an amount to pay: record the payment."))
        visit.write({'paid_free': True, 'paid_on': fields.Datetime.now(), 'paid_by_id': self.env.uid})
        visit.message_post(body=_("No charge for this repair (confirmed by %s).", self.env.user.name),
                           subtype_xmlid='mail.mt_note')
        return True

    def _co_missing(self):
        """What still stops the finish, in words."""
        self.ensure_one()
        visit = self.sudo()
        missing = []
        if not visit._co_no_fault() and not visit.after_photo_ids.filtered('image'):    # nothing repaired: no photo
            missing.append(_("Photo of the repaired device"))
        if not visit.paid_on:
            missing.append(_("Payment"))
        return missing

    def _co_finish(self, code=None, skip_reason=None):
        """The customer's finish code (or a manager's reason): the visit is done, the job card
        completed and the receipt sent. Returns {'ok', 'error'?, 'message'?, 'tries_left'?};
        a wrong code never raises, so the try counter is kept."""
        self._co_require()
        visit = self.sudo()
        if skip_reason is None:
            missing = visit._co_missing()
            if missing:
                return {'ok': False, 'error': 'missing', 'message': _("Still to do: %s", ', '.join(missing))}
            if visit.finish_tries >= MAX_CODE_TRIES:
                return {'ok': False, 'error': 'locked', 'tries_left': 0,
                        'message': _("Too many wrong codes. The office can finish the visit.")}
            if not code or str(code).strip() != (visit.finish_code or ''):
                visit.finish_tries += 1
                left = MAX_CODE_TRIES - visit.finish_tries
                return {'ok': False, 'error': 'wrong_code', 'tries_left': left,
                        'message': _("Wrong code. %s tries left.", left)}
        today = fields.Date.context_today(self)
        no_fault = visit._co_no_fault()
        days = 0 if no_fault else (visit.company_id or self.env.company).fix_warranty_days   # nothing repaired
        visit.write({'close_stage': 'closed', 'finished_on': fields.Datetime.now(),
                     'finish_skip_reason': skip_reason or False,
                     'warranty_until': fields.Date.add(today, days=days) if days and days > 0 else False})
        card = visit.job_card_id
        if card and card.state not in ('completed', 'cancelled'):
            # as the job card's own "Complete" (done): the customer's "completed" message, the booking Done.
            # No fault found: quietly - the customer gets the no-fault receipt below instead
            Wizard = self.env['job.card.completion.wizard'].sudo().with_context(wb_silent=no_fault)
            Wizard.create({'job_card_id': card.id, 'result': 'done'}).action_confirm()
        order = visit.order_id
        if no_fault and order and order.state not in ('done', 'cancelled'):
            order._set_state('done')
        if visit.state != 'done':
            visit.action_done()
        visit._co_send_receipt()
        visit.message_post(body=(_("Finished without the customer's code by %(who)s: %(why)s",
                                   who=self.env.user.name, why=skip_reason) if skip_reason
                                 else _("Finished with the customer's code.")), subtype_xmlid='mail.mt_note')
        return {'ok': True}

    def _co_send_receipt(self):
        self.ensure_one()
        visit = self.sudo()
        link = visit._co_rate_link()
        if visit._co_no_fault():
            visit.with_context(osm_extra={'paid': visit._co_paid_text(), 'recheck': visit._vr_recheck_line(),
                                          'rate_url': link})._fs_notify('visit_no_fault_receipt')
            return
        warranty = (_("Warranty: your repair is covered until %s.", visit.warranty_until.strftime('%a %d %b %Y'))
                    if visit.warranty_until else '')
        visit.with_context(osm_extra={'paid': visit._co_paid_text(), 'warranty': warranty,
                                      'rate_url': link})._fs_notify('visit_receipt')

    # ------------------------------------------------------------------ the rating
    def _co_rate_link(self):
        """The link to rate this visit (made once), or '' when the website has no address."""
        self.ensure_one()
        visit = self.sudo()
        site = visit._fs_site()
        track = site._track_url() if site else ''
        base = track[:-len('/track')] if track.endswith('/track') else track
        if not base:
            return ''
        if not visit.rate_token:
            visit.rate_token = secrets.token_urlsafe(18)
        return '%s/rate?v=%s&t=%s' % (base, quote(visit.name, safe=''), visit.rate_token)

    @api.model
    def _co_from_rate_link(self, host, ref, token):
        site = self.env['online.service.site']._for_host(host)
        if not site or not ref or not token:
            return self.browse()
        visit = self.sudo().search([('name', '=', str(ref)[:30]), '|', ('site_id', '=', site.id),
                                    ('order_id.site_id', '=', site.id)], limit=1)
        if not visit or not visit.rate_token or not hmac.compare_digest(visit.rate_token, str(token)):
            return self.browse()
        return visit

    def _co_rate_view(self):
        self.ensure_one()
        visit = self.sudo()
        company = visit.company_id or self.env.company
        return {
            'ok': True,
            'ref': visit.name,
            'order': visit.order_id.name or '',
            'customer': visit.customer_name or visit.order_id.customer_name or '',
            'technician': visit.technician_id.name or '',
            'rated': bool(visit.rated_on),
            'rating': visit.rating or 0,
            'review_url': (company.fix_review_url or '') if (visit.rating or 0) >= 4 else '',
        }

    @api.model
    def rate_options(self, host, ref, token):
        """The rating page (website server, bot key)."""
        self.env['online.service.order']._check_website_caller()
        visit = self._co_from_rate_link(host, ref, token)
        return visit._co_rate_view() if visit else {'ok': False, 'error': 'unknown'}

    @api.model
    def rate_answer(self, host, ref, token, stars, note=''):
        """1-5 stars and a few words, once."""
        self.env['online.service.order']._check_website_caller()
        visit = self._co_from_rate_link(host, ref, token)
        if not visit:
            return {'ok': False, 'error': 'unknown'}
        if visit.rated_on:
            return visit._co_rate_view()
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            stars = 0
        if not 1 <= stars <= 5:
            return dict(visit._co_rate_view(), ok=False, error='stars')
        note = (note or '').strip()[:1000]
        visit.write({'rating': stars, 'rating_note': note or False, 'rated_on': fields.Datetime.now()})
        visit.message_post(body=_("Customer rated the visit %(stars)s/5. %(note)s", stars=stars, note=note),
                           subtype_xmlid='mail.mt_note')
        return visit._co_rate_view()

    # ------------------------------------------------------------------ what the customer sees
    def _fs_track_block(self):
        out = super()._fs_track_block()
        visit = self.sudo()
        if visit.close_stage == 'finish' and visit.state == 'in_progress':
            out['close'] = {'finishing': True, 'finish_code': visit.finish_code or None}
        elif visit.close_stage == 'closed':
            out['close'] = {
                'finishing': False,
                'paid': visit._co_paid_text() if visit.paid_on else None,
                'warranty_until': fields.Date.to_string(visit.warranty_until) if visit.warranty_until else None,
                'rate_url': None if visit.rated_on else (visit._co_rate_link() or None),
                'rating': visit.rating or None,
            }
        return out

    # ------------------------------------------------------------------ the technician's page
    def _co_view(self):
        self.ensure_one()
        visit = self.sudo()
        currency = visit._co_currency()
        due = visit._co_due()
        return {
            'photos': len(visit.after_photo_ids.filtered('image')),
            'photos_max': MAX_AFTER_PHOTOS,
            'due': due,
            'currency': currency.name,
            'decimals': currency.decimal_places,
            'to_pay': currency.compare_amounts(due, 0.0) > 0,
            'with_tax': visit._co_with_tax(),       # "incl. VAT" by the amount
            'methods': [{'id': m.id, 'name': m.name, 'default': m.is_default} for m in visit._co_methods()],
            'paid': bool(visit.paid_on),
            'paid_text': visit._co_paid_text() if visit.paid_on else '',
            'tries_left': max(MAX_CODE_TRIES - visit.finish_tries, 0),
            'missing': visit._co_missing(),
            'no_fault': visit._co_no_fault(),      # no photo step, the visit fee only
        }

    def _co_steps(self):
        """The technician's progress strip: Assigned -> On the way -> Arrived -> Working ->
        Finish -> Done, each with its time."""
        self.ensure_one()
        visit = self.sudo()
        finish_at = visit.check_result_on if visit.close_stage else False
        rows = [('assigned', _("Assigned"), visit.assigned_on), ('on_the_way', _("On the way"), visit.departed_on),
                ('arrived', _("Arrived"), visit.arrived_on), ('in_progress', _("Working"), visit.started_on),
                ('finish', _("Finish"), finish_at), ('done', _("Done"), visit.done_on)]
        steps, current = [], False
        for key, label, at in rows:
            done = bool(at)
            is_current = not done and not current and visit.state not in ('done', 'cancelled', 'draft')
            current = current or is_current
            steps.append({'key': key, 'label': label, 'at': _iso(at), 'done': done, 'current': is_current})
        return steps

    def _co_device(self):
        """The device in words: the job card's brand and model, else what was booked."""
        self.ensure_one()
        visit = self.sudo()
        card = visit.job_card_id
        if card and card.brand_id:
            return card._fix_device_name()
        line = visit.order_id.line_ids[:1]
        return ' '.join(x for x in (line.device, line.model) if x) if line else ''

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
        visit = self.sudo()
        view['steps'] = visit._co_steps()
        view['problem'] = visit.order_id.problem or ''
        view['device'] = visit._co_device()
        if visit.close_stage == 'finish' and visit.state == 'in_progress':
            view.pop('result', None)
            view['close'] = visit._co_view()
        if visit.close_stage == 'closed':
            view['closed'] = {'paid_text': visit._co_paid_text() if visit.paid_on else '',
                              'warranty_until': fields.Date.to_string(visit.warranty_until) if visit.warranty_until else '',
                              'rating': visit.rating or 0}
        return view

    def _co_tech_act(self, action, args):
        if action == 'close_photo':
            self._co_photo(args.get('data'))
        elif action == 'close_clear':
            self._co_clear_photos()
        elif action == 'close_pay':
            self._co_pay(args.get('method_id'), args.get('amount'))
        elif action == 'close_free':
            self._co_free()
        elif action == 'close_code':
            return self._co_finish(code=args.get('code'))
        else:
            raise UserError(_("Unknown action."))
        return {'ok': True}

    def _fs_tech_do(self, action='', **args):
        """Adds Finish (the close_* steps) to the technician's steps; "What did you find?" is shut
        once the repair is done."""
        visit = self.sudo()
        finishing = visit.close_stage == 'finish' and visit.state == 'in_progress'
        if action.startswith('result_') and finishing:
            return dict(visit._fs_tech_view(), ok=False, error='close',
                        message=_("The repair is done: finish the visit (photo, payment, code)."))
        if not action.startswith('close_'):
            return super()._fs_tech_do(action, **args)
        if not finishing:
            return dict(visit._fs_tech_view(), ok=False, error='state',
                        message=_("This is done after the repair, to finish the visit."))
        try:
            with self.env.cr.savepoint():
                result = visit._co_tech_act(action, args)
        except (UserError, ValidationError) as err:
            return dict(visit._fs_tech_view(), ok=False, error='close', message=str(err))
        if not result.get('ok'):
            return dict(visit._fs_tech_view(), **result)
        return visit._fs_tech_view()

    # ------------------------------------------------------------------ the office
    def action_finish_without_code(self, reason):
        """The Booking Desk: a manager finishes the visit without the customer's code."""
        self.ensure_one()
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_manager'):
            raise AccessError(_("Only a manager can finish a visit without the customer's code."))
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("Write why the visit is finished without the customer's code."))
        visit = self.sudo()
        if visit.close_stage == 'finish' and not visit.paid_on:
            raise UserError(_("Record the payment (or \"No charge\") first."))
        result = visit._co_finish(skip_reason=reason)
        if not result.get('ok'):
            raise UserError(result.get('message') or _("Could not finish the visit."))
        return True

    def _co_thumbs(self, size=160):
        """Small pictures of the visit's photos (before and after), for My Visits."""
        self.ensure_one()
        out = []
        for photo in self.sudo().env['fix.visit.check.photo'].search(
                [('visit_id', '=', self.id), ('image', '!=', False)], order='kind, sequence, id'):
            try:
                small = image_process(base64.b64decode(photo.image), size=(size, size))
            except Exception:  # noqa: BLE001 - a broken picture is left out
                continue
            out.append({'id': photo.id, 'kind': photo.kind, 'name': photo.name,
                        'uri': 'data:%s;base64,%s' % (guess_mimetype(small, default='image/jpeg'),
                                                      base64.b64encode(small).decode())})
        return out
