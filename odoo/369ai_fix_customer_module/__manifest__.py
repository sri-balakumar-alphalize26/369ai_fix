# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix - Online Service',
    'version': '19.0.1.0.0',
    'summary': 'Website repair orders (Doorstep / Pickup) inside IT & Mobile Repair, '
               'with an alarm, WhatsApp status messages and OTP order tracking',
    'description': """
Orders placed on the repair website (danatfix.com and any other site listed
under Online Service > Configuration > Websites) arrive here.

* IT & Mobile Repair > Online Service: Doorstep Service, Pickup & Service,
  All Orders. One click turns an order into a Job Card.
* An alarm rings on every Odoo page until a new order is opened.
* The customer gets a WhatsApp message at every status (order and job card),
  through the WhatsApp gateway if it is installed.
* The website's "My orders" page logs the customer in with a code sent on
  WhatsApp and shows the live status.
* Which website may send to this database is configured per database
  (Configuration > Websites), so another site can feed another database.

Only this module's own files are used: mobile_repair and the WhatsApp
gateway are called, never changed.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['mobile_repair', 'mail', 'bus'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/online_message_data.xml',
        'views/online_order_views.xml',
        'views/online_site_views.xml',
        'views/online_message_views.xml',
        'views/job_card_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '369ai_fix_customer_module/static/src/online_alarm_service.js',
            '369ai_fix_customer_module/static/src/dashboard_online.xml',
        ],
    },
    'installable': True,
    'application': False,
}
