# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix - Website Booking',
    'version': '19.0.1.0.0',
    'summary': 'Website bookings become filled job cards: device tree and repairs from Odoo, '
               'customer account and address, photos and video',
    'description': """
The website books against Odoo's own catalogue (device category > brand > series >
model, and the repair services for that device). Each booking becomes an Online
Service order and, straight away, one job card per device - filled with the device,
the issue types and the repair lines with their prices, the customer's own words and
any photos or video. The order stays New, so the alarm rings and staff review it.

The customer is the 369 Mart account they signed in with, and the address one of
their saved addresses.

Only this module's files are used: IT & Mobile Repair, Online Service, the field
service visits and 369 Mart's sign-in and addresses are extended, never changed.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': [
        '369ai_fix_repair_module',
        '369ai_fix_customer_module',
        '369ai_fix_field_service',
        'mart369_auth',
        'mart369_address',
        'mart369_whatsapp_bridge',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/online_message_data.xml',
        'wizard/review_wizard_views.xml',
        'views/online_order_views.xml',
        'views/booking_slot_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '369ai_fix_web_booking/static/src/dashboard_bookings.xml',
        ],
    },
    'installable': True,
    'application': False,
}
