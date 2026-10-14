# Doorstep Visits (part of the 369ai_fix add-on, folder visits/)

This module tracks the technician's trip to the customer for doorstep orders. It is found under IT & Mobile Repair ▸ Online Service ▸ **Doorstep Visits**.

- **Depends on:** the customer part of `369ai_fix` (folder `customer/`), `mobile_repair`, `hr`, `mail`.
- **Nothing else changes:** no files in `mobile_repair`, the customer module or `partner_app` are edited.

## Flow

| Step | How | Sets | WhatsApp |
|---|---|---|---|
| Visit created | Confirming a doorstep order, or **Schedule Visit** on an order or job card | address, area, customer point | – |
| **Assign** | Needs a technician; it defaults to the job card's *Assigned To* | `assigned_on`, 4-digit `arrival_code` | `tech_assigned` (with `{code}`) |
| **On the way** | Button (later: the Partner App) | `departed_on`, `start_lat/lng` | `on_the_way` (with `{eta}`) |
| **Arrived** | The customer's code is typed in (setting); the office can skip it | `arrived_on`, `arrived_distance_m` | `arrived` |
| **Start work** / **Done** | Buttons, or the job card moving to inspection / completed | `started_on`, `done_on` | – |

The texts are under Online Service ▸ Configuration ▸ Status Messages. They can use these placeholders: `{technician}`, `{technician_phone}`, `{eta}` and `{code}`.

The settings are under IT & Mobile Repair settings ▸ **Doorstep Visits**:
- average speed (for the ETA)
- "signal lost" after N seconds
- trail keep-days
- arrival code on/off
- whether the technician's phone is shown to the customer

## Locations

**Customer.** `website_create` now keeps the `lat`/`lng` the website already sends; before, it was only turned into a map link. Staff can also paste a Google Maps or WhatsApp link, or type `lat, lng`, on the visit.

**Technician.** Call `visit._fs_record_position(lat, lng, accuracy, heading, speed, battery)`.
- It updates the live point.
- It adds a trail point only after a 25 m move.
- It accepts positions only while the visit is assigned, on the way, arrived or working.

  Nothing calls it yet. The **369 Partner App** link comes later, in a separate bridge module. That module will:
  - set `partner_app`'s `SERVICE_JOB_MODEL = 'fix.service.visit'`;
  - add `/api/service/*`, which calls `_fs_record_position`, `action_on_the_way` and `_fs_arrive(code=...)`.

**Distance and ETA.** Distance is a straight line. The ETA is distance ÷ speed, rounded up, and is shown only while the technician is on the way.

## For the website's /track page

`online.service.order.customer_orders(host, phone)` (what `/api/my-orders` returns) now adds a `visit` key to each order: `null` when there is no visit, otherwise:

```json
{"ref": "VIS/00012", "state": "on_the_way", "state_label": "Technician on the way",
 "steps": [{"key": "assigned", "label": "Technician assigned", "at": "2026-10-13T09:02:00Z", "done": true, "current": false},
           {"key": "on_the_way", "label": "On the way", "at": "2026-10-13T09:10:00Z", "done": true, "current": true},
           {"key": "arrived", "label": "Reached your place", "at": null, "done": false, "current": false},
           {"key": "in_progress", "label": "Repair in progress", "at": null, "done": false, "current": false},
           {"key": "done", "label": "Visit completed", "at": null, "done": false, "current": false}],
 "slot": {"start": "2026-10-13T09:00:00Z", "end": "2026-10-13T11:00:00Z"},
 "technician": {"name": "Arjun Rao", "phone": "+968...", "photo": "data:image/png;base64,..."},
 "live": {"lat": 23.59, "lng": 58.41, "fix_on": "2026-10-13T09:14:40Z", "age_s": 14, "stale": false},
 "dest": {"lat": 23.61, "lng": 58.45},
 "distance_km": 4.2, "eta_minutes": 9, "eta_at": "2026-10-13T09:24:00Z",
 "arrival_code": "4821"}
```

**What is shown when:**
- `technician` appears from Assigned onwards. Its `phone` and `photo` appear only while the visit is open.
- `live`, `dest`, `distance_km` and the ETA fields appear only while the technician is on the way or arrived. `stale` turns true after the "signal lost" setting.
- `arrival_code` appears only until the code is checked.
- Times are in UTC.

## Tests

```powershell
& "C:\Program Files\Odoo 19.0.20260119\python\python.exe" odoo-bin -c odoo.conf -d <test db> -i 369ai_fix `
  --addons-path="<odoo addons>,C:\Projects\Websites\369ai_fix\odoo" `
  --test-enable --test-tags=/369ai_fix --stop-after-init --http-port=8311 --gevent-port=8312 --max-cron-threads=0
```

WhatsApp is faked at `online.service.site._wa_send`, so the tests use no network.
