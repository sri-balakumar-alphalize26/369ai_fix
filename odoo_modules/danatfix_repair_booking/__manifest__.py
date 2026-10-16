# -*- coding: utf-8 -*-
{
    'name': 'Danat Fix Repair Booking',
    'version': '19.0.3.1.0',
    'summary': 'Alarms and the staff WhatsApp poll for website repair bookings',
    'description': """
Website bookings (IT & Mobile Repair > Online Service, each already a filled job
card) are handled here.

* The Booking Desk of the 369 ai Fix app shows every booking with Approve / Call
  (Main, Alternative) / Reject, "calling the customer" and the WhatsApp poll state.
  The old Live Screen is folded into it (its menu is archived; the action stays).
* Two alarms on every Odoo page: a chime while a booking waits for review, and a
  second tone when a customer books the visit time. They stay quiet while the
  Booking Desk is open, which rings them itself.
* The staff WhatsApp group gets each booking with a poll:
  Accept / Call customer first / Reject. The first tap decides; the screen follows.
  Reject from WhatsApp asks for the reason on the screen; Accept that needs a price
  or parts is sent to the screen.
* Bookings from before 19.0.2 stay under Old Bookings.
""",
    'author': 'Alphalize',
    'category': 'Sales',
    'depends': ['sales_automation', 'sales_automation_store', 'mail', 'bus', '369ai_fix'],
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
