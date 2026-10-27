# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.res_company import BILL_TYPES


class ApproveWizard(models.TransientModel):
    _name = 'wb.approve.wizard'
    _description = 'Approve a website booking'

    order_id = fields.Many2one('online.service.order', required=True, ondelete='cascade')
    technician_id = fields.Many2one('hr.employee', string='Technician',
                                    help="Replaces the placeholder on the job card(s).")
    parts_html = fields.Html('Parts', compute='_compute_parts', sanitize=False)
    has_missing = fields.Boolean(compute='_compute_parts')
    days = fields.Integer('Parts arrive in about (days)')
    # with tax (Easy Sales) or without (Estimate Sale): the booking's, the company's by default
    bill_type = fields.Selection(BILL_TYPES, 'Bill', compute='_compute_bill_type', store=True, readonly=False,
                                 help="With tax: the customer sees and approves the price including VAT.")
    # No job card yet (the booking came without a brand): staff choose the device here and the
    # job card is made with the booked repairs and their prices, then approved.
    needs_card = fields.Boolean(compute='_compute_needs_card')
    category_id = fields.Many2one('device.category', compute='_compute_needs_card')
    brand_id = fields.Many2one('device.brand', string='Brand', compute='_compute_device', store=True,
                               readonly=False, domain="[('category_id', '=', category_id)]")
    model_id = fields.Many2one('device.model', string='Model', compute='_compute_device', store=True,
                               readonly=False, domain="[('series_id.brand_id', '=', brand_id)]",
                               help="Leave empty when the customer doesn't know it.")

    @api.depends('order_id')
    def _compute_bill_type(self):
        for wiz in self:
            wiz.bill_type = wiz.order_id._wb_bill_type() if wiz.order_id else False

    def _brandless_lines(self):
        self.ensure_one()
        return self.order_id.sudo().line_ids.filtered(lambda l: not l.brand_id)

    def _device_line(self):
        self.ensure_one()
        return self._brandless_lines().filtered('category_id')[:1] if self.order_id else self.order_id.line_ids

    @api.depends('order_id')
    def _compute_needs_card(self):
        for wiz in self:
            order = wiz.order_id
            wiz.needs_card = bool(order) and not order.job_card_ids.filtered(lambda c: c.state != 'cancelled')
            wiz.category_id = wiz._device_line().category_id

    # kept apart from the one above: reading needs_card must not reset what staff chose
    @api.depends('order_id')
    def _compute_device(self):
        for wiz in self:
            line = wiz._device_line()
            # the customer's "Brand Model" text, matched as the booking itself does
            brand, _series, model = wiz.order_id._wb_match_device(line.category_id, line.model)
            wiz.brand_id = brand
            wiz.model_id = model

    @api.depends('order_id')
    def _compute_parts(self):
        for wiz in self:
            order = wiz.order_id
            if not order:
                wiz.parts_html, wiz.has_missing = False, False
                continue
            missing = order._wb_missing_parts()
            rows = []
            for line in order.sudo().job_card_ids.spare_part_line_ids:
                have = line.product_id.qty_available
                ok = line not in missing
                rows.append(Markup('<tr><td>%s</td><td class="text-end">%s</td><td>'
                                   '<span class="badge %s">%s</span></td></tr>') % (
                    line.description or line.product_id.display_name, line.quantity,
                    'text-bg-success' if ok else 'text-bg-danger',
                    _("%s in stock", have) if ok else _("none - must be ordered")))
            # no parts yet is normal: the technician picks them at the visit (by the problem found)
            wiz.parts_html = (Markup('<table class="table table-sm"><tbody>%s</tbody></table>')
                              % Markup('').join(rows)) if rows else False
            wiz.has_missing = bool(missing)

    def action_confirm(self):
        self.ensure_one()
        if self.bill_type and self.bill_type != self.order_id._wb_bill_type():
            self.order_id._wb_set_bill_type(self.bill_type)
        if self.needs_card:
            self._make_job_card()
        elif self.has_missing and self.days <= 0:
            raise UserError(_("How many days until the missing parts arrive? The customer is told."))
        self.order_id._wb_do_approve(technician=self.technician_id, days=self.days)
        return {'type': 'ir.actions.act_window_close'}

    def _make_job_card(self):
        """The device staff chose goes on the booking's lines that have none, then the job
        card is made as a booking makes it (the booked repairs with their prices)."""
        if not self.brand_id:
            raise UserError(_("This booking has no job card yet: choose the brand (and the model if "
                              "you know it), and the job card is made with the booked repairs."))
        model = self.model_id if self.model_id.series_id.brand_id == self.brand_id else self.model_id.browse()
        order = self.order_id.sudo()
        for line in self._brandless_lines().filtered(
                lambda l: not l.category_id or l.category_id == self.brand_id.category_id):
            vals, product = order._wb_device({
                'category_id': self.brand_id.category_id.id, 'brand_id': self.brand_id.id,
                'series_id': model.series_id.id, 'model_id': model.id, 'product_id': line.product_id.id})
            vals['product_id'] = product.id or False
            if model:
                vals['model'] = '%s %s' % (self.brand_id.name, model.name)
            line.write(vals)
        order._wb_make_job_cards()
        if not order.job_card_ids.filtered(lambda c: c.state != 'cancelled'):
            raise UserError(_("The job card could not be made: use Create Job Card on the booking."))


class RejectWizard(models.TransientModel):
    _name = 'wb.reject.wizard'
    _description = 'Reject a website booking'

    order_id = fields.Many2one('online.service.order', required=True, ondelete='cascade')
    reason = fields.Text(required=True, help="Sent to the customer on WhatsApp and kept on the Rejected list.")

    def action_confirm(self):
        self.ensure_one()
        self.order_id._wb_do_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class OfficeWizard(models.TransientModel):
    _name = 'wb.office.wizard'
    _description = 'Take the device to the office'

    job_card_id = fields.Many2one('job.card', required=True, ondelete='cascade')
    accessory_ids = fields.Many2many('device.accessory', string='Accessories received')
    no_accessories = fields.Boolean('No accessories (device only)')
    accessories = fields.Text('Accessories notes')
    return_by = fields.Date('Return by', required=True,
                            default=lambda self: fields.Date.add(fields.Date.context_today(self), days=3))
    # counted, so the office and the customer can check every item comes back
    accessory_count = fields.Char('Taken', compute='_compute_accessory_count')

    @api.depends('accessory_ids', 'no_accessories')
    def _compute_accessory_count(self):
        for wiz in self:
            n = 0 if wiz.no_accessories else len(wiz.accessory_ids)
            wiz.accessory_count = _("Device only") if not n else (_("1 accessory") if n == 1 else _("%s accessories", n))

    def action_confirm(self):
        self.ensure_one()
        if not self.accessory_ids and not self.no_accessories:
            raise UserError(_("Tick the accessories you are taking with the device, or \"No accessories\"."))
        card = self.job_card_id
        notes = self.accessories or ''
        if self.no_accessories and not self.accessory_ids:
            notes = (notes + '\n' if notes else '') + _("No accessories - device only.")
        card.write({
            'accessory_ids': [(6, 0, self.accessory_ids.ids)],
            'accessories': notes or False,
            'wb_at_office': True,
            'wb_taken_on': fields.Datetime.now(),
            'wb_taken_by_id': self.env.uid,
            'wb_return_by': self.return_by,
        })
        for visit in card.env['fix.service.visit'].sudo().search(
                [('job_card_id', '=', card.id), ('state', 'not in', ('done', 'cancelled'))]):
            try:
                with self.env.cr.savepoint():
                    visit.action_done()
            except Exception:  # noqa: BLE001 - a visit in an unexpected state stays as it is
                visit.message_post(body=_("Device taken to the office."))
        card.message_post(body=_("Device taken to the office by %(who)s, to return by %(date)s. Accessories: %(acc)s",
                                 who=self.env.user.name, date=self.return_by,
                                 acc=card._wb_accessories_text()))
        # wb_office_silent: the caller sends its own message (the technician's result, visits/)
        if card.online_order_id and not self.env.context.get('wb_office_silent'):
            # the customer's receipt: what was taken, by whom, and when it comes back
            card.online_order_id._wb_notify('office_taken', date=self.return_by.strftime('%d %b'),
                                            accessories=card._wb_accessories_text(),
                                            technician=card._wb_taken_by_name())
        # an approved quotation's "take to the office" (visits/): tell the customer when it comes back
        if self.env.context.get('fix_visit_take'):
            self.env['fix.service.visit'].browse(self.env.context['fix_visit_take'])._vr_after_take(self.return_by)
        return {'type': 'ir.actions.act_window_close'}


class ReceiveWizard(models.TransientModel):
    """The office confirms the device taken by the technician arrived, with which accessories."""
    _name = 'wb.receive.wizard'
    _description = 'Device received at the office'

    job_card_id = fields.Many2one('job.card', required=True, ondelete='cascade')
    taken = fields.Char('The technician took', compute='_compute_taken')
    accessory_ids = fields.Many2many('device.accessory', string='Arrived with it',
                                     compute='_compute_taken', store=True, readonly=False,
                                     help="Untick anything the technician ticked that did not arrive.")
    note = fields.Char('Note', help="e.g. \"Scratch on the back\" or \"Charger cable only\".")

    @api.depends('job_card_id')
    def _compute_taken(self):
        for wiz in self:
            card = wiz.job_card_id.sudo()
            # "Naveen - 3 accessories (Stylus, SIM card, Power adapter)": the office counts against it
            wiz.taken = '%s - %s' % (card.wb_taken_by_id.name or '', card._wb_accessories_text()) if card else ''
            wiz.accessory_ids = card.accessory_ids

    def action_confirm(self):
        self.ensure_one()
        self.job_card_id._wb_receive(self.accessory_ids, self.note)
        return {'type': 'ir.actions.act_window_close'}


class CallWizard(models.TransientModel):
    _name = 'wb.call.wizard'
    _description = 'Call the customer'

    order_id = fields.Many2one('online.service.order', required=True, ondelete='cascade')
    main_number = fields.Char(compute='_compute_numbers')
    alt_number = fields.Char(compute='_compute_numbers')

    @api.depends('order_id')
    def _compute_numbers(self):
        for wiz in self:
            numbers = dict((label, number) for label, number in wiz.order_id._wb_numbers())
            wiz.main_number = numbers.get(_('Main'), '')
            wiz.alt_number = numbers.get(_('Alternative'), '')

    def action_call_main(self):
        return self.order_id._wb_tel(self.main_number)

    def action_call_alt(self):
        return self.order_id._wb_tel(self.alt_number)
