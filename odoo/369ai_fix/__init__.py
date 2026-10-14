# -*- coding: utf-8 -*-
# One add-on, one folder per part. The order matters: each part extends the ones
# before it (job.card.write, website_create, website_catalog, ... call super()),
# exactly as when they were separate add-ons depending on each other.
from . import customer   # website orders, alarm, WhatsApp status messages, order tracking
from . import repair     # repairs as IT & Mobile Repair services, visit fee + quote
from . import visits     # technician visits: on the way, arrived, position, ETA, arrival code
from . import booking    # website booking -> filled job card, account, address, slots
from . import website    # pictures for the website ("Fix Website" app)
from . import app        # the "369 ai Fix" home-screen app: dashboard and menus

from .app import uninstall_hook


def post_init_hook(env):
    """On a fresh install: the repair catalogue first, then the website's starter pictures."""
    repair.post_init_hook(env)
    website.post_init_hook(env)
