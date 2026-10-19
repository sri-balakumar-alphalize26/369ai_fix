# -*- coding: utf-8 -*-
"""19.0.2.13.0: quote first, always (as on Urban Company). The quotation message now
says what happens once the customer approves ({timeline}); the "device at the office,
part on order" message is sent after the approval. Only texts nobody edited change."""

TEXTS = [
    ('quote_changed', 'Hi {name}, after checking your device the price for {order} has changed:\n{estimate}\n(estimate was {old_total}). Please approve or decline: {quote_url}',
     'Hi {name}, our technician checked your device for {order}. Here is the price:\n{estimate}\n{timeline}\nPlease approve or decline - nothing is done before your OK: {quote_url}'),
    ('office_part_wait', "Hi {name}, your {device} is with us for {order}. Once you approve the price we order the part (about {part_days} days); the repair then takes {within}. We'll bring it back by {date}.",
     "Thanks {name}! Your {device} is with us for {order}. The part is ordered (about {part_days} days) and the repair then takes {within}. We'll bring it back by {date}."),
]


def migrate(cr, version):
    for key, old, new in TEXTS:
        cr.execute("UPDATE online_service_message SET body = %s WHERE key = %s AND body = %s", (new, key, old))
