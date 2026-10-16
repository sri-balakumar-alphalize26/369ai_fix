# -*- coding: utf-8 -*-
"""19.0.2.6.0: no more "OMR 0" on the website. A repair without a price shows "Price after
check", and {price} in texts becomes the visit fee (or "price after check"). Reword the starter
texts that still say OMR 0 - only where they are exactly as loaded, so staff edits stay."""
from odoo import SUPERUSER_ID, api

# (old starter text, new starter text) - the same as website/data/starter_content.json now
COPYRIGHT = ('© 2026 Danat Fix. All rights reserved. · Estimates shown as OMR 0 — pricing to be announced.',
             '© {year} Danat Fix. All rights reserved.')
MOST_BOOKED_LINE = ('Doorstep or pickup · estimate OMR 0', 'Doorstep or pickup · price confirmed before any work')
TRUST_LINE = ('Technician visit {price}', 'Visit fee: {price}')
FAQ_ANSWER = ('No. Diagnosis and the visit or pickup are shown as {price} — you get an estimate before any work starts.',
              'The technician checks your device and tells you the price before any work starts — nothing is done without your OK. Visit fee: {price}.')


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for site in env['online.service.site'].with_context(active_test=False).search([]):
        if site.footer_copyright == COPYRIGHT[0]:
            site.footer_copyright = COPYRIGHT[1]
        if site.cov_trust:
            lines = site.cov_trust.split('\n')
            new = [TRUST_LINE[1] if line.strip() == TRUST_LINE[0] else line for line in lines]
            if new != lines:
                site.cov_trust = '\n'.join(new)
    sections = env['fix.home.section'].with_context(active_test=False).search([('kind', '=', 'services')])
    sections.filtered(lambda s: s.text == MOST_BOOKED_LINE[0]).write({'text': MOST_BOOKED_LINE[1]})
    faqs = env['fix.site.faq'].with_context(active_test=False).search([])
    faqs.filtered(lambda f: f.answer == FAQ_ANSWER[0]).write({'answer': FAQ_ANSWER[1]})
