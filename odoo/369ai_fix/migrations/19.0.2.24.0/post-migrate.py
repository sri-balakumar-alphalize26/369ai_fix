# -*- coding: utf-8 -*-
"""19.0.2.24.0: "No fault found" - the customer's message adds the free re-check line ({recheck}).
The default text changes only where staff never edited it (the messages are noupdate)."""
from odoo import SUPERUSER_ID, api

TEXTS = {
    'visit_no_repair': (
        "Hi {name}, {technician} has checked your device (order {order}).\n"
        "{reason}\n"
        "Thank you for choosing {site}.",
        "Hi {name}, {technician} has checked your device (order {order}).\n"
        "{reason}\n"
        "{recheck}\n"
        "Thank you for choosing {site}."),
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
