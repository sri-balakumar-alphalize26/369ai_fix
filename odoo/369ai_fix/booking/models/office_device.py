# -*- coding: utf-8 -*-
"""A customer's device at our office (taken for a lab check, or an approved "take"):

* the office confirms it arrived ("Received", with the accessories that came with it); until
  then the Booking Desk shows "On the way to the office";
* the customer's message and My orders say what was taken and by whom (`_wb_accessories_text`);
* a promised date that passed - the price after a lab check, or the return - shows as Overdue on
  the desk, and a daily job gives the office a to-do once (`_cron_wb_overdue`);
* the return visit done: the device is back with the customer (`wb_returned`).
"""
from odoo import _, api, fields, models


def accessories_text(accessories):
    """'3 accessories (A, B, C)', '1 accessory (A)' or 'the device only': counted, so the office
    and the customer can check every item comes back."""
    names = accessories.mapped('name')
    if not names:
        return _("the device only")
    if len(names) == 1:
        return _("1 accessory (%s)", names[0])
    return _("%(count)s accessories (%(names)s)", count=len(names), names=', '.join(names))


class JobCard(models.Model):
    _inherit = 'job.card'

    wb_received_on = fields.Datetime('Received at the office on', readonly=True, copy=False)
    wb_received_by_id = fields.Many2one('res.users', 'Received by', readonly=True, copy=False)
    wb_received_note = fields.Text('Received: note', readonly=True, copy=False)
    wb_received_accessory_ids = fields.Many2many(
        'device.accessory', 'job_card_wb_received_accessory_rel', 'card_id', 'accessory_id',
        string='Accessories received', readonly=True, copy=False)
    # the customer agreed to the lab check (on the link, My orders or at the door)
    wb_lab_ok = fields.Boolean('Customer agreed to the lab check', readonly=True, copy=False)
    # after a lab check: the date the customer was promised the price
    wb_price_by = fields.Date('Price promised by', readonly=True, copy=False)
    # the overdue to-dos already given (one per kind: "price", "return")
    wb_overdue_noted = fields.Char(readonly=True, copy=False)

    # ------------------------------------------------------------------ what was taken
    def _wb_accessories_text(self):
        """'3 accessories (Stylus, SIM card, Power adapter)' or 'the device only': what was taken with
        the device, counted, for the customer, the office and the job card."""
        self.ensure_one()
        return accessories_text(self.sudo().accessory_ids)

    def _wb_taken_by_name(self):
        """Who took the device: the visit's technician, else the job card's, else the user."""
        self.ensure_one()
        card = self.sudo()
        visit = card.fs_visit_ids.filtered(lambda v: v.technician_id).sorted('id')[-1:]
        return visit.technician_id.name or card.assigned_to.name or card.wb_taken_by_id.name or ''

    def _wb_office_state(self):
        """'on_way' (taken, not received yet), 'received', or '' (not at the office)."""
        self.ensure_one()
        card = self.sudo()
        if not card.wb_at_office or card.wb_returned:
            return ''
        return 'received' if card.wb_received_on else 'on_way'

    def _wb_overdue(self, today=None):
        """'price' (lab check: the price promised by a date that passed), 'return' (the return date
        passed and the repair is not finished), or ''."""
        self.ensure_one()
        card = self.sudo()
        if not card.wb_at_office or card.wb_returned or card.state in ('completed', 'cancelled'):
            return ''
        today = today or fields.Date.context_today(self)
        if card.wb_price_by and card.wb_price_by < today and card.quote_state not in ('waiting', 'accepted', 'declined'):
            return 'price'
        lab_waiting = card.wb_price_by and card.quote_state != 'accepted'
        if card.wb_return_by and card.wb_return_by < today and not lab_waiting:
            return 'return'
        return ''

    # ------------------------------------------------------------------ the office confirms it arrived
    def action_wb_receive(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Received at the office: %s", self.name),
            'res_model': 'wb.receive.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_job_card_id': self.id},
        }

    def _wb_receive(self, accessories, note=''):
        """The device and these accessories arrived at the office; anything ticked by the
        technician but missing is noted on the job card and the booking."""
        self.ensure_one()
        card = self.sudo()
        note = (note or '').strip()[:500]
        missing = card.accessory_ids - accessories
        card.write({'wb_received_on': fields.Datetime.now(), 'wb_received_by_id': self.env.uid,
                    'wb_received_note': note or False,
                    'wb_received_accessory_ids': [(6, 0, accessories.ids)]})
        body = _("Device received at the office by %(who)s, with: %(acc)s.",
                 who=self.env.user.name, acc=accessories_text(accessories))
        if missing:
            body += ' ' + _("Missing %(count)s: %(names)s.", count=len(missing), names=', '.join(missing.mapped('name')))
        if note:
            body += ' ' + note
        card.message_post(body=body)
        order = card.online_order_id
        if order:
            order.message_post(body=body)
            order._ring()
        return True

    # ------------------------------------------------------------------ overdue
    @api.model
    def _cron_wb_overdue(self):
        """Once a day: a to-do for each device whose promised date passed (once per kind)."""
        today = fields.Date.context_today(self)
        cards = self.sudo().search([('wb_at_office', '=', True), ('wb_returned', '=', False),
                                    ('state', 'not in', ('completed', 'cancelled'))])
        for card in cards:
            kind = card._wb_overdue(today)
            noted = (card.wb_overdue_noted or '').split(',')
            if not kind or kind in noted:
                continue
            order = card.online_order_id
            user = (order.approved_by_id if order else None) or card.create_uid or self.env.user
            summary = (_("Overdue: send the price for %s", card.name) if kind == 'price'
                       else _("Overdue: return the device for %s", card.name))
            note = (_("The customer was promised the price by %s.", card.wb_price_by) if kind == 'price'
                    else _("The customer was promised the device back by %s.", card.wb_return_by))
            card.activity_schedule('mail.mail_activity_data_todo', summary=summary, note=note, user_id=user.id)
            card.wb_overdue_noted = ','.join(x for x in noted + [kind] if x)
        return True


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    def action_done(self):
        """The visit that brings a device back from the office is done: it is with the customer."""
        res = super().action_done()
        for visit in self.sudo():
            card = visit.job_card_id
            if card and card.wb_at_office and not card.wb_returned and card.wb_taken_on \
                    and visit.create_date and visit.create_date > card.wb_taken_on:
                card.wb_returned = True
                card.message_post(body=_("Device returned to the customer (visit %s).", visit.name))
        return res
