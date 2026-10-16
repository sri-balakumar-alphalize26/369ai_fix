# -*- coding: utf-8 -*-
"""19.0.2.8.0: the pop-ups and the chat assistant are edited in Odoo (Fix Website > Pop-ups
& chat). Give every website today's wording: the announcement bar, welcome pop-up, flash
offer, cookie notice, Spin & Win prizes, chat replies and answers, slider slides and the
leaving panel. Only empty fields are filled; lists only where the site has none."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix.website.seed').load_starter_content(env)
