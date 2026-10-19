# -*- coding: utf-8 -*-
"""19.0.2.12.0: "fixed within N days" can be days or weeks: the part-in-office message
says {within} ("3 days", "2 weeks"). Only a text nobody edited is changed."""

OLD = "It will be fixed within {days} days, by {date}."
NEW = "It will be fixed within {within}, by {date}."


def migrate(cr, version):
    cr.execute("""
        UPDATE online_service_message
           SET body = replace(body, %s, %s)
         WHERE key = 'part_in_stock' AND body LIKE %s
    """, (OLD, NEW, '%' + OLD + '%'))
