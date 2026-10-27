# -*- coding: utf-8 -*-
"""After "Upgrade" of this app in Apps, Odoo reloads on the first app of the menu (here
Discuss, a near-empty page). Open the 369 ai Fix app on its Booking Desk instead."""
from odoo import models

OUR_MODULES = ('369ai_fix', 'danatfix_repair_booking')


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def button_immediate_upgrade(self):
        result = super().button_immediate_upgrade()
        if not (isinstance(result, dict) and result.get('tag') == 'reload'
                and set(self.mapped('name')) & set(OUR_MODULES)):
            return result
        menu = self.env.ref('369ai_fix.menu_fix_root', raise_if_not_found=False)
        desk = self.env.ref('369ai_fix.action_fix_desk', raise_if_not_found=False)
        if not menu:
            return result
        params = {'menu_id': menu.id}
        # the desk for the office; a technician-only user lands on the app (My Visits)
        if desk and self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
            params['action_id'] = desk.id
        return dict(result, params=params)
