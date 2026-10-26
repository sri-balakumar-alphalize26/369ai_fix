# -*- coding: utf-8 -*-
"""19.0.2.22.0: a day off needs a reason. Days off saved before without one read "Day off",
so the column can be made required (staff may write the real reason afterwards)."""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('fix_technician_day_off')")
    if cr.fetchone()[0]:
        cr.execute("UPDATE fix_technician_day_off SET reason = 'Day off' WHERE reason IS NULL OR btrim(reason) = ''")
