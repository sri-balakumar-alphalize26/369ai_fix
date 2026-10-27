# -*- coding: utf-8 -*-
"""19.0.2.23.0: a device taken to our office - the customer's message says what was taken
(the accessories) and by whom. The default texts change only where staff never edited them
(the messages are noupdate, so the upgrade itself leaves them as they are)."""
from odoo import SUPERUSER_ID, api

TEXTS = {
    'office_taken': (
        "Hi {name}, we've taken your device to our office for {order}. We'll send you the price shortly "
        "and return it by {date}.",
        "Hi {name}, our technician {technician} took your device to our office for {order}, with: {accessories}. "
        "We'll send you the price shortly and return it by {date}."),
    'office_part_wait': (
        "Thanks {name}! Your {device} is with us for {order}. The part is ordered (about {part_days} days) and the "
        "repair then takes {within}. We'll bring it back by {date}.",
        "Thanks {name}! Your {device} is with us for {order} ({technician} took it, with: {accessories}). The part is "
        "ordered (about {part_days} days) and the repair then takes {within}. We'll bring it back by {date}."),
    'visit_lab_check': (
        "Hi {name}, your {device} needs a closer check in our lab 🔬 (order {order}).\n"
        "{technician} has taken it with them. We will send you the price within {days}, before any repair.",
        "Hi {name}, your {device} needs a closer check in our lab 🔬 (order {order}).\n"
        "{technician} has taken it with them, with: {accessories}. We will send you the price within {days} "
        "(by {date}), before any repair."),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Message = env['online.service.message'].with_context(active_test=False)
    for key, (old, new) in TEXTS.items():
        for msg in Message.search([('key', '=', key)]):
            if (msg.body or '').strip() == old:
                msg.body = new
