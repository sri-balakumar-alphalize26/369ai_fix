# partner_app (369 Partner App): Delivery and Service roles

The partner app now covers two kinds of work:
- **Delivery**: today's riders.
- **Service**: on-site repair and install visits.

Each person on the rider record (`sa.delivery.partner`) works in Delivery, Service, or both, and signs in once.

- **Depends on** `sales_automation_delivery` only. Nothing in `sales_automation_*` or `delivery_rider_rpc` is edited.
- **Installing it changes nothing at first.** Every existing rider starts as **Delivery**.
- **Own riders only.** Kind (Own Rider / Delivery Partner) is the delivery module's field. It is left untouched, but hidden here: on the rider form and in both rider lists. New riders keep its default, Own Rider.

## Works In

On the rider form there is a new field, **Works In**:

| Works In | Delivery offers | Service visits |
|---|---|---|
| Delivery (default) | yes | no |
| Service | **never** | yes, once the service module is installed |
| Delivery and Service | yes | yes, once the service module is installed |

**Where the office sets it.** Delivery managers get a top menu, **Partner App ▸ Partners**:
- **The list** shows Name, Phone, Works In and Busy.
- **Filters:** Delivery, Service, Both.
- **Grouping:** by Works In.

**The rider form.** It reads, top to bottom:
- Phone;
- **Works In**, on its own highlighted band;
- Busy, read-only, shown as "Free" or "On a delivery · OUT/00014";
- Shops.

The same form also opens from Delivery ▸ Configuration ▸ Riders & Couriers, with Kind hidden there too.

## One busy lock across both lines

**Busy** (shown on the rider form) is worked out like this:

| Busy | When |
|---|---|
| On a delivery | the person holds a delivery job: offered, accepted, picked, dispatched, out for delivery, or coming back |
| On a service visit | **Service Visit In Hand** is set |
| Free | anything else |

The service side sets **Service Visit In Hand** when an agent accepts a visit, and clears it when the visit ends. Until the service module is on the database, nothing sets it.

**Nobody gets a delivery they can't take.** Every delivery offer goes through `stock.picking.sa_action_offer`, whoever chose the rider:
- the delivery module at confirm;
- an add-on at Packed;
- clocking on;
- the office.

If the chosen person is Service-only or out on a visit, the offer goes to the next person who can take it. If there is nobody, the job goes back to To Dispatch. A note on the job says why.

The pick itself filters people out in two ways:
- it searches under a context flag, so whichever `_sa_pick_for` runs (the delivery module's own, `delivery_rider_rpc`'s, or `delivery_fleet_ops`'s) never sees them;
- it also passes them as `rider_rpc_exclude`, which those add-ons already honour.

**Clocking on** sweeps up waiting deliveries, but not for a Service-only person or someone on a visit.

## API

```http
GET /api/partner/me
Authorization: Bearer <token from /api/delivery/auth/verify-code>
X-Odoo-Database: <db>
```

```json
{"success": true, "rider_id": 7, "work_type": "both", "work_type_label": "Delivery and Service",
 "lines": ["delivery"], "busy_line": "none", "busy_ref": null,
 "service_available": false, "server_time": "2026-10-09T10:00:00Z"}
```

- **`lines`** lists the workspaces the app should open. Service appears in it only when `service_available` is true.
- **Not signed in**: 401 `unauthorized`.
- **A server without this module**: 404. The app reads that as "Delivery only".

## When the service module arrives

The service side switches on by itself when the service module's job model is on the same database. That model's name goes in `SERVICE_JOB_MODEL` in `models/sa_delivery_partner.py`. It is `None` until the senior's module is known.

The parts still to come:
- offering a visit to free Service and Both agents;
- accepting it with a row lock, refused if the agent holds a delivery;
- `/api/service/*`.

## Tests

```powershell
& "C:\Program Files\Odoo 19.0.20260119\python\python.exe" odoo-bin -c odoo.conf -d <db> -i partner_app `
  --addons-path="<odoo addons>,C:\Projects\APK's\369Delivery_partner\odoo_modules" `
  --test-enable --test-tags=/partner_app --stop-after-init --http-port=8211 --gevent-port=8212 --max-cron-threads=0
```

Run it from PowerShell, because Git Bash mangles `--test-tags`. WhatsApp is faked at `stock.picking._sa_session`, so no network is used.
