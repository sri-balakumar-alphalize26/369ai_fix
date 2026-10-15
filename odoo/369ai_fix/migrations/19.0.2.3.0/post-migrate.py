# -*- coding: utf-8 -*-
"""19.0.2.3.0: one repair flow instead of a Doorstep / Pickup choice. The technician always
comes first; if it can't be fixed on the spot, it goes to our lab and comes back. The two
"Doorstep / pickup cards" lines become the visit (its last step = fixed on the spot) and the
"needs a part or more work" branch. Old default wording is replaced only where staff haven't
changed it. Pickup coverage zones are kept; the website just doesn't show them."""
from odoo import SUPERUSER_ID, api

OLD_CARDS = [
    ({'name': 'Doorstep Service', 'extra': 'We repair it at your door', 'value': 'Technician at your door in about 60 minutes',
      'text': 'Book a slot\nTechnician arrives\nRepaired on the spot'},
     {'name': 'We come to you', 'extra': 'Our technician visits at the time you pick',
      'value': 'Technician at your door in about 60 minutes', 'text': 'Book a slot\nTechnician visits\nFixed on the spot ✓'}),
    ({'name': 'Pickup & Service', 'extra': 'We collect, repair and return it', 'value': 'Picked up same day, back in 24–48 hours',
      'text': 'Rider picks up\nRepaired in our lab\nDelivered back'},
     {'name': 'Needs a part or more work', 'extra': 'Price confirmed with you first', 'value': 'Back in 24–48 hours',
      'text': 'Taken to our lab\nRepaired\nDelivered back'}),
]
OLD_SITE = {
    'svc_modes_eyebrow': ('Choose your service', 'How it works'),
    'svc_modes_title': ('How should we reach you?', 'We come to you first'),
    'svc_fee_label': ('Visit / pickup fee', 'Visit fee'),
    'svc_title2': ('or we pick it up.', 'on the spot or in our lab.'),
    'svc_lead': ('Choose how you want the service done, check that we reach your area, then pick your device.',
                 'Our technician comes to you first. Check that we reach your area, then pick your device and repairs.'),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Section = env['fix.home.section'].with_context(active_test=False)
    for section in Section.search([('kind', '=', 'modes')]):
        lines = section.line_ids.with_context(active_test=False).sorted('sequence')
        for line, (old, new) in zip(lines, OLD_CARDS):
            vals = {f: new[f] for f, v in old.items() if (line[f] or '').strip() == v}
            if vals:
                line.write(vals)
        if section.button1_link and section.button1_link.startswith('/services?mode='):
            section.button1_link = '/services#coverage'
    for site in env['online.service.site'].with_context(active_test=False).search([]):
        vals = {f: new for f, (old, new) in OLD_SITE.items() if (site[f] or '') == old}
        if site.cov_trust and 'Visit or pickup {price}' in site.cov_trust:
            vals['cov_trust'] = site.cov_trust.replace('Visit or pickup {price}', 'Technician visit {price}')
        if vals:
            site.write(vals)
