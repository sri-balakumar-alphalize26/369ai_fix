# -*- coding: utf-8 -*-
"""19.0.2.25.0: Labour only has no default any more - the technician chooses Free or a charge
(`labour_set`). Visits already on Labour only were free by default, so they count as chosen."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE fix_service_visit SET labour_set = TRUE WHERE check_outcome = 'labour'")
