# -*- coding: utf-8 -*-
"""19.0.2.2.0: the Services page wording, coverage areas, FAQs and info pages are edited
in Odoo too. Load them from the starter content (the site as it was in code), so the
website looks the same after the upgrade. Only empty places are filled."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').load_starter_content(env)
