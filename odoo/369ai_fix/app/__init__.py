# -*- coding: utf-8 -*-
from . import models

# The old Online Service menu under IT & Mobile Repair; archived by app/views/menus.xml.
OLD_MENUS = [
    '369ai_fix.menu_online_service_root',
]


def uninstall_hook(env):
    """Put the old Online Service menu back."""
    for xmlid in OLD_MENUS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.active = True
