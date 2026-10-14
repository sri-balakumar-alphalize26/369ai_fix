# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class ServiceVisitPosition(models.Model):
    """Where the technician has been on a visit: the trail on the map."""
    _name = 'fix.service.visit.position'
    _description = 'Doorstep Visit Position'
    _order = 'recorded_on desc, id desc'
    _rec_name = 'visit_id'

    visit_id = fields.Many2one('fix.service.visit', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='visit_id.company_id', store=True)
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    accuracy = fields.Float('Accuracy (m)')
    recorded_on = fields.Datetime(required=True, index=True, default=fields.Datetime.now)

    @api.autovacuum
    def _gc_old_positions(self):
        """Forget trail points older than each company's keep-days."""
        now = fields.Datetime.now()
        for company in self.env['res.company'].sudo().search([]):
            days = company.fs_position_keep_days
            if days and days > 0:
                self.sudo().search([
                    ('company_id', '=', company.id),
                    ('recorded_on', '<', now - timedelta(days=days)),
                ]).unlink()
