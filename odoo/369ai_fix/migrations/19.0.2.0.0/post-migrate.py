# -*- coding: utf-8 -*-
"""19.0.2.0.0: the six 369ai_fix_* add-ons became this one (tools/merge_old_modules.sql
renames the database records first). A database that had only some of them, e.g. only
the customer one, gets the install-time data of the parts it never installed. Each part
runs only when its data is missing, so a database that had them all is left as it is."""
import importlib
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    addon = importlib.import_module('odoo.addons.369ai_fix')
    Template = env['product.template'].with_context(active_test=False)
    if not Template.search_count([('repair_category_ids', '!=', False)]):
        _logger.info('369ai_fix: no repair services yet, loading the repair catalogue')
        addon.repair.post_init_hook(env)
    if not env['fix.web.image'].search_count([]):
        _logger.info('369ai_fix: no website pictures yet, loading the starter pictures')
        addon.website.post_init_hook(env)
