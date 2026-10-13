"""19.0.1.1.0 -> 19.0.1.2.0: phones/tablets/watches filed under the wrong category are
moved, issue types get their device categories (plus the AI package's extra types),
and the website's repair services get their issue types back."""
import importlib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    importlib.import_module('odoo.addons.369ai_fix_repair_module.hooks').run_data_fixes(env)
