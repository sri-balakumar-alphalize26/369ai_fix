# -*- coding: utf-8 -*-
"""19.0.2.21.0: the places in a time window follow the technicians. Staff with the Technician
role are ticked "Takes doorstep visits", and every slot's typed number becomes 0 ("At most":
no cap), so each window holds as many visits as there are technicians that day."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.booking.models.technician_day_off').tick_technicians(env)
    cr.execute("UPDATE fix_booking_slot SET capacity = 0")
