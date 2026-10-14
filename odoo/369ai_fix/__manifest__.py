# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix',
    'version': '19.0.2.1.0',
    'summary': 'The doorstep repair service in one add-on: website orders and bookings, '
               'repair catalogue, technician visits, website pictures and the 369 ai Fix app',
    'description': """
Everything the 369 ai Fix website and its staff need, in one add-on (until
October 2026 these were six add-ons; each is now a folder here):

* **customer/**: orders placed on the repair website (Doorstep / Pickup) arrive
  in Odoo; an alarm rings until a new order is opened; the customer gets a
  WhatsApp message at every status; "My orders" on the website logs in with a
  code sent on WhatsApp. Which website may send to this database is set under
  Configuration > Websites.
* **repair/**: repairs are IT & Mobile Repair's own Services, with device
  categories, and per-model prices through Brand / Series / Model. The job card
  offers only the matching services. Optional "Visit fee + quote" in the repair
  settings.
* **visits/**: every doorstep order gets a technician visit: assigned, on the
  way, arrived, live position, distance and ETA, arrival code.
* **booking/**: the website books against Odoo's own catalogue; each booking
  becomes an order and a filled job card (device, repairs with prices, the
  customer's words, photos and video). The customer is their 369 Mart account
  and one of their saved addresses. Review, approve / reject, time slots.
* **website/**: the "Fix Website" app, for whoever looks after the website:
  device photos or drawings, brand logos, photos for every repair service.
* **app/**: the "369 ai Fix" home-screen app: dashboard, bookings, service,
  catalogue and configuration.

The Live Screen, alarms and the staff WhatsApp poll are in
danatfix_repair_booking, which adds its menus to the 369 ai Fix app.

mobile_repair and 369 Mart's add-ons are extended, never changed.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': [
        'mobile_repair',
        'mail',
        'bus',
        'hr',
        'mart369_auth',
        'mart369_address',
        'mart369_whatsapp_bridge',
    ],
    # Same order as when these were separate add-ons: customer, repair, visits, booking, website, app.
    'data': [
        # customer
        'customer/security/ir.model.access.csv',
        'customer/data/ir_sequence.xml',
        'customer/data/online_message_data.xml',
        'customer/views/online_order_views.xml',
        'customer/views/online_site_views.xml',
        'customer/views/online_message_views.xml',
        'customer/views/job_card_views.xml',
        'customer/views/menus.xml',
        # repair
        'repair/data/product_category_data.xml',
        'repair/views/product_template_views.xml',
        'repair/views/job_card_views.xml',
        'repair/views/res_config_settings_views.xml',
        # visits
        'visits/security/ir.model.access.csv',
        'visits/security/security.xml',
        'visits/data/ir_sequence.xml',
        'visits/data/online_message_data.xml',
        'visits/wizard/arrival_code_wizard_views.xml',
        'visits/views/service_visit_views.xml',
        'visits/views/online_order_views.xml',
        'visits/views/job_card_views.xml',
        'visits/views/res_config_settings_views.xml',
        'visits/views/menus.xml',
        # booking
        'booking/security/ir.model.access.csv',
        'booking/data/online_message_data.xml',
        'booking/wizard/review_wizard_views.xml',
        'booking/views/online_order_views.xml',
        'booking/views/booking_slot_views.xml',
        # website
        'website/security/security.xml',
        'website/security/ir.model.access.csv',
        'website/views/fix_web_image_views.xml',
        'website/views/device_views.xml',
        'website/views/service_views.xml',
        'website/views/online_site_views.xml',
        'website/views/home_views.xml',
        'website/views/site_content_views.xml',
        'website/views/menus.xml',
        # app
        'app/views/dashboard_action.xml',
        'app/views/job_card_actions.xml',
        'app/views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '369ai_fix/static/src/customer/online_alarm_service.js',
            '369ai_fix/static/src/customer/dashboard_online.xml',
            '369ai_fix/static/src/booking/dashboard_bookings.xml',
            '369ai_fix/static/src/app/dashboard_hide.xml',
            '369ai_fix/static/src/app/fix_dashboard.css',
            '369ai_fix/static/src/app/fix_dashboard.js',
            '369ai_fix/static/src/app/fix_dashboard.xml',
            '369ai_fix/static/src/website/device_pictures.css',
            '369ai_fix/static/src/website/device_pictures.js',
            '369ai_fix/static/src/website/device_pictures.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}
