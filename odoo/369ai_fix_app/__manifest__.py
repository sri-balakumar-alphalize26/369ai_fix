# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix',
    'version': '19.0.1.0.0',
    'summary': 'One app for the doorstep repair service: website bookings, Live Screen, '
               'job cards, visits, catalogue and settings',
    'description': """
A home-screen app that gathers the whole 369 ai Fix service flow in one place:

* **Dashboard** (opens first): same look as the IT & Mobile Repair dashboard,
  with website bookings, website job cards by state, online orders, doorstep
  visits and completed repairs per month. Each number opens its list.
* **Live Screen**: the booking desk (the alarm rings anywhere in Odoo).
* **Bookings**: doorstep and pickup orders, waiting for approval, visit time
  booked, waiting for parts, rejected, old bookings.
* **Service**: job cards that came from the website, doorstep visits and
  spare requests.
* **Catalogue**: repair services, spare parts, device categories, brands,
  series, models, issue types and accessories.
* **Configuration**: time slots, websites, status messages, booking desk and
  repair settings.

Menus only: the records are still mobile_repair's and the 369 ai Fix modules'.
Their old menus under IT & Mobile Repair > Online Service and Store > Website
Bookings, and the two Online Service boxes on the IT & Mobile Repair dashboard,
are hidden while this app is installed and come back if it is uninstalled.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': [
        '369ai_fix_customer_module',
        '369ai_fix_repair_module',
        '369ai_fix_web_booking',
        '369ai_fix_field_service',
        'danatfix_repair_booking',
    ],
    'data': [
        'views/dashboard_action.xml',
        'views/job_card_actions.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '369ai_fix_app/static/src/dashboard_hide.xml',
            '369ai_fix_app/static/src/fix_dashboard.css',
            '369ai_fix_app/static/src/fix_dashboard.js',
            '369ai_fix_app/static/src/fix_dashboard.xml',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}
