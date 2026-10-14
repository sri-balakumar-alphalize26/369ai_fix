# -*- coding: utf-8 -*-
"""19.0.2.1.0: the website's texts (home page, contact, branches, footer) are edited in
Odoo. Load the starter content, i.e. the site as it was in code, so the website looks the
same after the upgrade."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').load_starter_content(env)
