{
    'name': '369 Partner App',
    'version': '19.0.1.1.0',
    'category': 'Inventory/Delivery',
    'summary': 'Delivery and Service roles for the partner app, with one busy lock',
    'description': """
One partner app, two lines of work: **Delivery** (today's riders) and
**Service** (on-site repair and install visits). Each person on the rider
record works in Delivery, Service, or both, with one login.

* **Works In** on the rider record: Delivery, Service, or Delivery and
  Service. Everyone starts as Delivery, so installing this changes nothing
  for the riders already there.
* **No delivery offers to the wrong people.** A Service-only agent, or anyone
  out on a service visit, is never offered a delivery - however the rider was
  chosen (by the delivery module, by another add-on, or at clock-on).
* **`GET /api/partner/me`** tells the app which lines this person works in
  and whether they are busy, signed in with the same token as
  `/api/delivery/*`.
* **`GET /api/partner/country`**, before sign-in: the company's country, so
  the app's number field opens on the right dialling code.
* **Test rider** tick: a made-up number signs in with the fixed code 111111,
  and no WhatsApp message is ever sent to it.

The service side (offers, accept with a lock, `/api/service/*`) joins the
moment the service module is on the same database; until then this module is
the role and the delivery-side lock only.

Depends on `sales_automation_delivery` only. Nothing in `sales_automation_*`
or `delivery_rider_rpc` is edited, and uninstalling this puts everything back.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': ['sales_automation_delivery'],
    'data': [
        'views/sa_delivery_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
