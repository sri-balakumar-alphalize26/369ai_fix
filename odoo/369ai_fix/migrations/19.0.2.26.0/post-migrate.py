# -*- coding: utf-8 -*-
"""19.0.2.26.0: the line under each repair's name on the website ("Cracked or broken
screen") comes from the service's Sales Description in Odoo. Give the services the website
already shows today's line; only empty ones are filled."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').fill_repair_captions(env)
