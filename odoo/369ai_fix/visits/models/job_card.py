# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class JobCard(models.Model):
    """Shows the doorstep visit on the job card and keeps it in step."""
    _inherit = 'job.card'

    fs_visit_ids = fields.One2many('fix.service.visit', 'job_card_id', string='Doorstep visits')
    fs_visit_count = fields.Integer(compute='_compute_fs_visit_count')

    @api.depends('fs_visit_ids')
    def _compute_fs_visit_count(self):
        for card in self:
            card.fs_visit_count = len(card.fs_visit_ids)

    def write(self, vals):
        before = {card.id: card.state for card in self} if 'state' in vals else {}
        res = super().write(vals)
        if before:
            for card in self.filtered('fs_visit_ids'):
                if card.state != before.get(card.id):
                    try:
                        card.fs_visit_ids._fs_on_job_card_state(card.state)
                    except Exception:  # noqa: BLE001 - never block the job card itself
                        _logger.exception("Doorstep visit: status update for %s failed", card.name)
        if 'assigned_to' in vals:
            # A new technician on the card takes over visits that have not left yet.
            for card in self:
                card.fs_visit_ids.filtered(lambda v: v.state in ('draft', 'assigned')).sudo().write(
                    {'technician_id': card.assigned_to.id})
        return res

    def action_fs_schedule_visit(self):
        self.ensure_one()
        if self.state in ('completed', 'cancelled'):
            raise UserError(_("This job card is closed."))
        open_visit = self.fs_visit_ids.filtered(lambda v: v.state != 'cancelled')[:1]
        if open_visit:
            return open_visit._fs_form_action()
        order = self.online_order_id
        if order:
            vals = order._fs_visit_vals()
        else:
            partner = self.partner_id
            vals = {
                'company_id': self.company_id.id or self.env.company.id,
                'partner_id': partner.id,
                'customer_name': partner.name,
                'phone': self.phone or partner.phone,
                'area': partner.street2 or partner.city or False,
                'address': partner.street or False,
            }
            if partner.partner_latitude or partner.partner_longitude:
                vals.update({'customer_lat': partner.partner_latitude,
                             'customer_lng': partner.partner_longitude,
                             'customer_location_source': 'staff'})
        vals.update({'job_card_id': self.id, 'technician_id': self.assigned_to.id})
        return self.env['fix.service.visit'].create(vals)._fs_form_action()

    def action_fs_view_visits(self):
        self.ensure_one()
        if self.fs_visit_count == 1:
            return self.fs_visit_ids._fs_form_action()
        action = self.env['ir.actions.act_window']._for_xml_id(
            '369ai_fix.action_service_visit')
        action['domain'] = [('job_card_id', '=', self.id)]
        return action
