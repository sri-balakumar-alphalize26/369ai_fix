# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ApproveWizard(models.TransientModel):
    _name = 'wb.approve.wizard'
    _description = 'Approve a website booking'

    order_id = fields.Many2one('online.service.order', required=True, ondelete='cascade')
    technician_id = fields.Many2one('hr.employee', string='Technician',
                                    help="Replaces the placeholder on the job card(s).")
    parts_html = fields.Html('Parts', compute='_compute_parts', sanitize=False)
    has_missing = fields.Boolean(compute='_compute_parts')
    days = fields.Integer('Parts arrive in about (days)')

    @api.depends('order_id')
    def _compute_parts(self):
        for wiz in self:
            order = wiz.order_id
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
            wiz.parts_html = (Markup('<table class="table table-sm"><tbody>%s</tbody></table>')
                              % Markup('').join(rows)) if rows else escape(_("No spare parts on the job card."))
            wiz.has_missing = bool(missing)

    def action_confirm(self):
        self.ensure_one()
        if self.has_missing and self.days <= 0:
            raise UserError(_("How many days until the missing parts arrive? The customer is told."))
        self.order_id._wb_do_approve(technician=self.technician_id, days=self.days)
        return {'type': 'ir.actions.act_window_close'}


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
                                 acc=', '.join(self.accessory_ids.mapped('name')) or _("none")))
        # wb_office_silent: the caller sends its own message (the technician's result, visits/)
        if card.online_order_id and not self.env.context.get('wb_office_silent'):
            card.online_order_id._wb_notify('office_taken', date=self.return_by.strftime('%d %b'))
        # an approved quotation's "take to the office" (visits/): tell the customer when it comes back
        if self.env.context.get('fix_visit_take'):
            self.env['fix.service.visit'].browse(self.env.context['fix_visit_take'])._vr_after_take(self.return_by)
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
