# -*- coding: utf-8 -*-
"""19.0.2.5.0: the "Popular:" links under the home search bar are edited in Odoo (lines of the
top banner with role "popular"). Give existing home pages today's five links."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').load_starter_content(env)
