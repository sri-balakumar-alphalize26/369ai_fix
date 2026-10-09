# -*- coding: utf-8 -*-
{
    'name': 'Danat Fix Repair Booking',
    'version': '19.0.1.0.0',
    'summary': 'Website repair bookings on the Store screen, with an alarm and a WhatsApp poll for the staff group',
    'description': """
Every "Book" button on the Danat Fix / 369 ai Fix website sends the booking here.

* Store > Website Bookings > Live Screen: cards for new bookings, with an
  alarm that keeps ringing until somebody accepts one. The alarm also rings
  on every other Odoo page (polled every 20 s, pushed over the bus at once).
* The staff WhatsApp group gets the booking and a poll:
  Accept / Call customer first / Reject. The first tap decides, and the
  Store screen updates by itself.
* The website talks to Odoo through the normal external API
  (execute_kw on danatfix.booking.website_create) with a dedicated user and
  an API key - see the README of the website.
""",
    'author': 'Alphalize',
    'category': 'Sales',
    'depends': ['sales_automation', 'sales_automation_store', 'mail', 'bus'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/booking_views.xml',
        'views/settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'danatfix_repair_booking/static/src/booking_shared.js',
            'danatfix_repair_booking/static/src/booking_alarm_service.js',
            'danatfix_repair_booking/static/src/booking_screen.js',
            'danatfix_repair_booking/static/src/booking_screen.xml',
            'danatfix_repair_booking/static/src/booking_screen.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
