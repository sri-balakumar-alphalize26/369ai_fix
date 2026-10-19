# -*- coding: utf-8 -*-
"""One settings record: where the staff poll goes and how the alarm sounds."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DanatfixBookingSettings(models.Model):
    _name = 'danatfix.booking.settings'
    _description = 'Website Booking Settings'

    name = fields.Char(default='Website Booking Settings', readonly=True)

    # ---- WhatsApp staff group -------------------------------------------
    poll_enabled = fields.Boolean(
        'Send WhatsApp poll', default=True,
        help="Post every new booking to the staff group with an "
             "Accept / Call customer first / Reject poll. The first tap "
             "decides; the Store screen follows.")
    staff_group_id = fields.Many2one(
        'sa.sales.group', string='Staff group',
        help="A WhatsApp group already synced under Sales Automation. "
             "It does not need the Sales Automation tick - the bot never "
             "answers in it, only this module posts there.")
    staff_group_jid = fields.Char(
        'Or group JID',
        help="Use this when the group is not in the list: its WhatsApp "
             "address, like 120363xxxxxxxx@g.us.")
    session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp session',
        help="The number that posts the poll. Empty: the staff group's own "
             "session, or the first active one.")

    # ---- Alarm 1: a new booking (chime) -----------------------------------
    new_alarm_on = fields.Boolean(
        'Ring for new bookings', default=True,
        help="Rings while a website booking waits in New, until someone presses Call, "
             "Approve or Reject.")
    ring_seconds = fields.Integer(
        'Ring for (seconds)', default=20,
        help="How long each burst of the alarm lasts.")
    repeat_seconds = fields.Integer(
        'Pause between rings (seconds)', default=15)
    alarm_user_ids = fields.Many2many(
        'res.users', 'danatfix_booking_alarm_user_rel', 'settings_id',
        'user_id', string='Who hears it',
        domain=[('share', '=', False)],
        help="Empty: every internal user hears it on any Odoo page. The Booking "
             "Desk always rings for whoever has it open.")

    # ---- Alarm 2: the customer booked the visit time (second tone) --------
    slot_alarm_on = fields.Boolean(
        'Ring when a visit time is booked', default=True,
        help="Rings when a customer picks the visit time from the WhatsApp link, until "
             "someone presses Seen.")
    slot_ring_seconds = fields.Integer(
        'Ring for (seconds)', default=20,
        help="How long each burst of the alarm lasts.")
    slot_repeat_seconds = fields.Integer('Pause between rings (seconds)', default=15)
    slot_alarm_user_ids = fields.Many2many(
        'res.users', 'danatfix_booking_slot_alarm_user_rel', 'settings_id',
        'user_id', string='Who hears it ',
        domain=[('share', '=', False)],
        help="Empty: every internal user hears it on any Odoo page. The Booking "
             "Desk always rings for whoever has it open.")

    def _alarm_sound(self):
        """Both alarms as the pages play them: on/off, ring and pause in seconds."""
        self.ensure_one()
        return {
            'new_on': self.new_alarm_on,
            'ring': max(3, self.ring_seconds or 20),
            'repeat': max(3, self.repeat_seconds or 15),
            'slot_on': self.slot_alarm_on,
            'slot_ring': max(3, self.slot_ring_seconds or 20),
            'slot_repeat': max(3, self.slot_repeat_seconds or 15),
        }

    desk_replaces_online_alarm = fields.Boolean(
        'Only the Live Screen alarm rings', default=True,
        help="Website orders ring with this module's alarm (new booking + visit time booked). "
             "Online Service's own alarm stays quiet, so staff hear one alarm, not two.")

    @api.model
    def get_settings(self):
        settings = self.sudo().search([], limit=1)
        if not settings:
            settings = self.sudo().create({})
        return settings

    # ---- What the poll uses ---------------------------------------------
    def _group_jid(self):
        self.ensure_one()
        return (self.staff_group_id.group_jid or self.staff_group_jid or '').strip()

    def _session(self):
        self.ensure_one()
        if self.session_id:
            return self.session_id
        if self.staff_group_id.session_id:
            return self.staff_group_id.session_id
        Session = self.env['whatsapp.session'].sudo()
        return Session.search([('use_whatsapp', '=', True)], limit=1) \
            or Session.search([], limit=1)

    def action_test_group(self):
        """Post one line in the staff group, so the setup is proven before a
        customer depends on it."""
        self.ensure_one()
        jid = self._group_jid()
        session = self._session()
        if not jid:
            raise UserError(_("Choose the staff group (or type its JID) first."))
        if not session:
            raise UserError(_("No WhatsApp session found."))
        try:
            session.send_message(jid, _(
                "🔔 Test from Odoo: website repair bookings will be posted "
                "in this group with an Accept / Call / Reject poll."))
        except Exception as err:  # noqa: BLE001 - a queued send is fine too
            if type(err).__name__ != 'WhatsAppQueued':
                raise UserError(_("WhatsApp refused the message: %s", err))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Sent"),
                'message': _("Check the staff group on WhatsApp."),
                'type': 'success',
            },
        }

    @api.model
    def action_open_settings(self):
        settings = self.get_settings()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Website Booking Settings"),
            'res_model': self._name,
            'res_id': settings.id,
            'view_mode': 'form',
            'target': 'current',
        }
