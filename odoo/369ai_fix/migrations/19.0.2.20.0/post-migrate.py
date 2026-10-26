# -*- coding: utf-8 -*-
"""19.0.2.20.0: Spin & Win gets a backend (Odoo picks the prize by chance %). Prizes made
before this had no chance, so nothing could be won: the starter chances go on the starter
prizes of a website whose prizes all still have 0, by their code. Edited prizes keep their
own chance."""
import json

from odoo.tools import file_open

MODULE = '369ai_fix'


def migrate(cr, version):
    with file_open(f'{MODULE}/website/data/starter_content.json') as f:
        starter = json.load(f)
    by_code = {x['code']: x for x in starter.get('popups', {}).get('wheel', []) if x.get('code')}
    cr.execute("""
        SELECT site_id FROM fix_site_item WHERE kind = 'wheel'
         GROUP BY site_id HAVING COALESCE(MAX(chance), 0) = 0
    """)
    for (site_id,) in cr.fetchall():
        for code, x in by_code.items():
            cr.execute("""
                UPDATE fix_site_item SET chance = %s, free_visit = %s
                 WHERE site_id = %s AND kind = 'wheel' AND code = %s
            """, (int(x.get('chance') or 0), bool(x.get('free_visit')), site_id, code))
