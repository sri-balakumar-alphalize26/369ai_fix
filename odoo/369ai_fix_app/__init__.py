# -*- coding: utf-8 -*-
from . import models

# Old menus this app replaces; archived by views/menus.xml.
OLD_MENUS = [
    '369ai_fix_customer_module.menu_online_service_root',
    'danatfix_repair_booking.menu_danatfix_booking_root',
]


def uninstall_hook(env):
    """Put the old Online Service and Website Bookings menus back."""
    for xmlid in OLD_MENUS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.active = True
