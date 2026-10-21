# -*- coding: utf-8 -*-
"""19.0.2.15.0: at the visit the technician ticks what's wrong and is offered the parts that
fix it (as on Urban Company). Spare parts with no problems set get them, and the device
types they fit, from their names; staff check them on the Spare Parts screen."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.repair.part_problems').fill_part_problems(env)
