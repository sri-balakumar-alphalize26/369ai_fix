# -*- coding: utf-8 -*-
"""19.0.2.4.1: the section kind labels changed ("How we fix it" instead of "Doorstep / pickup
cards"); refresh the stored section names so lists and the editor read the same."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons import __path__ as _p  # noqa: F401
    import importlib
    KINDS = dict(importlib.import_module('odoo.addons.369ai_fix.website.models.home').KINDS)
    for section in env['fix.home.section'].with_context(active_test=False).search([]):
        name = KINDS.get(section.kind)
        if name and section.name != name:
            section.name = name
