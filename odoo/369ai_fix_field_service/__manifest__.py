# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix - Doorstep Visits',
    'version': '19.0.1.0.0',
    'summary': 'Technician visits to the customer: assigned, on the way, arrived, '
               'live position, distance and ETA, arrival code',
    'description': """
Every doorstep order gets a Visit (IT & Mobile Repair > Online Service >
Doorstep Visits) that holds the technician's trip to the customer:

* **Customer location**: the GPS point the website sends with the booking is
  kept (it used to be only a map link). Staff can paste a Google Maps link to
  set or correct it.
* **Technician**: assigned from the job card's "Assigned To", with photo and
  phone.
* **Steps with times**: Assigned, On the way, Arrived, Working, Done.
* **Live position**: the technician's last position, how old it is, a short
  trail, the straight-line distance to the customer and an ETA. The 369
  Partner App will send these positions later; this module stores them and
  shows them (one method, `_fs_record_position`, is the way in).
* **Arrival code**: a 4-digit code the customer reads out at the door.
* **Website tracking**: the website's "My orders" answer gets a `visit`
  block for doorstep orders (technician, live map point, ETA, steps, code).
* **WhatsApp**: Technician assigned, On the way and Arrived messages, editable
  under Online Service > Configuration > Status Messages.

mobile_repair, 369ai_fix_customer_module and the partner app are called,
never changed.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['369ai_fix_customer_module', 'mobile_repair', 'hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_sequence.xml',
        'data/online_message_data.xml',
        'wizard/arrival_code_wizard_views.xml',
        'views/service_visit_views.xml',
        'views/online_order_views.xml',
        'views/job_card_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
