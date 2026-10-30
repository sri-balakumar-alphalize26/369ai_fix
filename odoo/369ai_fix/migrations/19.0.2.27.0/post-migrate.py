# -*- coding: utf-8 -*-
"""19.0.2.27.0: the home tiles' name and order come from Odoo. Give each device type the
place its tile has on the site today (Home order), so nothing moves on the upgrade."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').fill_tile_order(env)
