# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class ServiceVisitArrival(models.TransientModel):
    """'Arrived' asks for the code the customer reads out at the door."""
    _name = 'fix.service.visit.arrival'
    _description = 'Doorstep Visit: arrival code'

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade')
    code = fields.Char('Code from the customer', size=4)
    message = fields.Char(readonly=True)

    def _reopen(self, message):
        self.message = message
        self.code = False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Customer's arrival code"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        # Not raising on a wrong code keeps the try counter (a raise rolls it back).
        result = self.visit_id._fs_arrive(code=self.code)
        if result.get('ok'):
            return {'type': 'ir.actions.act_window_close'}
        if result.get('error') == 'state':
            raise UserError(result.get('message'))
        return self._reopen(result.get('message'))

    def action_skip(self):
        """The office confirms the arrival without the code (customer not reachable, locked)."""
        self.ensure_one()
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_receptionist'):
            raise AccessError(_("Only the office can confirm an arrival without the code."))
        result = self.visit_id._fs_arrive(skip_code=True)
        if not result.get('ok'):
            raise UserError(result.get('message'))
        return {'type': 'ir.actions.act_window_close'}
