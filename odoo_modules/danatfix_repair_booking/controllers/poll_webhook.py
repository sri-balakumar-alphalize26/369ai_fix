# -*- coding: utf-8 -*-
"""Votes on the website-booking poll in the staff group.

Group traffic reaches `sales_automation`'s webhook (WhatsAppWebhookGroups).
Subclassing it here puts this check first: a vote whose poll id belongs to a
website booking is applied and stops; every other message - including every
vote on the sales bot's own polls - goes on to the bot exactly as before.
Odoo combines this class with any other subclass of the same controller
(sales_automation_insights has one), so nothing is replaced.
"""

import logging

from odoo.addons.sales_automation.controllers.group_webhook import (
    WhatsAppWebhookGroups,
)
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppWebhookBookingPoll(WhatsAppWebhookGroups):

    def _handle_message(self, session, payload, *args, **kwargs):
        try:
            if self._danatfix_booking_vote(session, payload):
                return None
        except Exception as err:  # noqa: BLE001 - the webhook must answer 200
            _logger.exception("Website booking: poll vote failed: %s", err)
        return super()._handle_message(session, payload, *args, **kwargs)

    def _danatfix_booking_vote(self, session, payload):
        """True when the message was a vote on one of our polls (handled)."""
        data = (payload or {}).get('data') or {}
        message = data.get('message') or {}
        if not isinstance(message, dict) or 'pollUpdateMessage' not in message:
            return False
        poll_ref = self._sa_poll_ref(message)
        if not poll_ref:
            return False
        booking = request.env['danatfix.booking'].sudo()._from_poll_ref(poll_ref)
        if not booking:
            return False
        choice = self._sa_poll_choice(message)
        key = data.get('key') or {}
        digits, _lid, _hidden = self._sa_sender_of(data, key)
        push_name = str(data.get('pushName') or '')
        if choice:
            changed = booking._apply_vote(choice, digits, push_name)
            _logger.info("Website booking %s: %s voted %r (%s)", booking.name,
                         push_name or digits or '(hidden)', choice,
                         'applied' if changed else 'too late, ignored')
        # A vote taken back arrives with no option at all: still ours, nothing to do.
        return True
