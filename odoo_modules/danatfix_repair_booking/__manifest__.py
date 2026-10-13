# -*- coding: utf-8 -*-
{
    'name': 'Danat Fix Repair Booking',
    'version': '19.0.2.0.0',
    'summary': 'Live Screen, alarms and the staff WhatsApp poll for website repair bookings',
    'description': """
Website bookings (IT & Mobile Repair > Online Service, each already a filled job
card) are handled here.

* Store > Website Bookings > Live Screen: a card per new booking with the device,
  the faults, the customer's own words and photos, the parts and their stock, and
  Approve / Call (Main, Alternative) / Reject. Booked visit times show too, with Seen.
* Two alarms on every Odoo page: a chime while a booking waits for review, and a
  second tone when a customer books the visit time.
* The staff WhatsApp group gets each booking with a poll:
  Accept / Call customer first / Reject. The first tap decides; the screen follows.
  Reject from WhatsApp asks for the reason on the screen; Accept that needs a price
  or parts is sent to the screen.
* Bookings from before 19.0.2 stay under Old Bookings.
""",
    'author': 'Alphalize',
    'category': 'Sales',
    'depends': ['sales_automation', 'sales_automation_store', 'mail', 'bus', '369ai_fix_web_booking'],
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
