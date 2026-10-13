# -*- coding: utf-8 -*-
{
    'name': '369 ai Fix - Repair Catalogue',
    'version': '19.0.1.2.0',
    'summary': "Repairs as IT & Mobile Repair services: device categories on products, "
               "matching services on the job card, optional visit fee + quote",
    'description': """
Repairs are IT & Mobile Repair's own Services (Products > Services), priced on
the product. This module only adds:

* Device categories on products. With the product's Brand / Series / Model
  (already in mobile_repair) a service can be general ("Screen replacement",
  Mobile Phone) or for one device ("Screen replacement - iPhone 13").
* On a job card, Required Services offers only the services that match the
  card's device category, brand, series and model.
* Settings > Inspection > Visit fee + quote: new job cards start as a Paid
  Inspection (the Inspection Charge Product is the visit fee), and the fee is
  waived when the quotation includes a repair.

On install it adds the CCTV Installation, Networking & Wi-Fi, Data Recovery
and IT Support device categories and the website's 65 repairs at price 0.

mobile_repair is extended, never changed.
""",
    'author': 'Alphalize',
    'category': 'Services',
    'license': 'LGPL-3',
    'depends': ['mobile_repair'],
    'data': [
        'data/product_category_data.xml',
        'views/product_template_views.xml',
        'views/job_card_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
