# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .geo import valid_fix
from .service_visit import LOCATION_SOURCES, STATES

_logger = logging.getLogger(__name__)


class OnlineServiceOrder(models.Model):
    """Keeps the customer's GPS point, and gives doorstep orders a Visit."""
    _inherit = 'online.service.order'

    customer_lat = fields.Float('Latitude', digits=(10, 7), readonly=True, copy=False)
    customer_lng = fields.Float('Longitude', digits=(10, 7), readonly=True, copy=False)
    location_accuracy = fields.Float('Accuracy (m)', readonly=True, copy=False)
    location_source = fields.Selection(LOCATION_SOURCES, string='Location from', readonly=True,
                                       copy=False)
    visit_ids = fields.One2many('fix.service.visit', 'order_id', string='Visits')
    visit_count = fields.Integer(compute='_compute_visit')
    visit_id = fields.Many2one('fix.service.visit', string='Visit', compute='_compute_visit')
    visit_state = fields.Selection(STATES, string='Visit status', compute='_compute_visit')

    @api.depends('visit_ids.state')
    def _compute_visit(self):
        for order in self:
            visit = order._fs_current_visit()
            order.visit_count = len(order.visit_ids)
            order.visit_id = visit
            order.visit_state = visit.state

    def _fs_current_visit(self):
        """The visit that counts: the newest not cancelled, else the newest."""
        self.ensure_one()
        visits = self.visit_ids.sorted('id', reverse=True)
        return visits.filtered(lambda v: v.state != 'cancelled')[:1] or visits[:1]

    # ------------------------------------------------------------------
    # The website door: keep the point it already sends
    # ------------------------------------------------------------------
    @api.model
    def website_create(self, payload):
        result = super().website_create(payload)
        if not (isinstance(result, dict) and result.get('ok') and not result.get('duplicate')
                and isinstance(payload, dict)):
            return result
        fix = valid_fix(payload.get('lat'), payload.get('lng'))
        if not fix:
            return result
        site = self.env['online.service.site']._for_host(payload.get('host'))
        order = self.sudo().search([('name', '=', result.get('ref')), ('site_id', '=', site.id)], limit=1)
        if order:
            try:
                accuracy = max(float(payload.get('accuracy') or 0.0), 0.0)
            except (TypeError, ValueError):
                accuracy = 0.0
            source = payload.get('location_source')
            order.write({
                'customer_lat': fix[0],
                'customer_lng': fix[1],
                'location_accuracy': accuracy,
                'location_source': source if source in dict(LOCATION_SOURCES) else 'website',
            })
        return result

    # ------------------------------------------------------------------
    # Visits
    # ------------------------------------------------------------------
    def _fs_visit_vals(self):
        self.ensure_one()
        job_card = self.job_card_id
        vals = {
            'order_id': self.id,
            'site_id': self.site_id.id,
            'company_id': (self.company_id or self.env.company).id,
            'partner_id': self.partner_id.id,
            'customer_name': self.customer_name,
            'phone': self.phone,
            'area': self.area,
            'address': self.address,
            'job_card_id': job_card.id,
            'technician_id': job_card.assigned_to.id,
        }
        if valid_fix(self.customer_lat, self.customer_lng):
            vals.update({
                'customer_lat': self.customer_lat,
                'customer_lng': self.customer_lng,
                'customer_accuracy': self.location_accuracy,
                'customer_location_source': self.location_source or 'website',
                'customer_location_on': self.create_date,
            })
        elif self.map_url:
            vals['customer_map_link'] = self.map_url
        return vals

    def _fs_ensure_visit(self):
        """A draft visit for each doorstep order that has none (cancelled ones count)."""
        Visit = self.env['fix.service.visit'].sudo()
        for order in self.sudo():
            if order.mode == 'doorstep' and not order.visit_ids:
                Visit.create(order._fs_visit_vals())

    def _set_state(self, state, notify_key=None):
        res = super()._set_state(state, notify_key)
        if state == 'confirmed':
            try:
                self._fs_ensure_visit()
            except Exception:  # noqa: BLE001 - never block the order itself
                _logger.exception("Doorstep visit: creating the visit for %s failed", self.mapped('name'))
        return res

    def action_schedule_visit(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_("Reopen the order first."))
        visit = self._fs_current_visit()
        if not visit or visit.state == 'cancelled':
            visit = self.env['fix.service.visit'].create(self._fs_visit_vals())
        return visit._fs_form_action()

    def action_view_visits(self):
        self.ensure_one()
        if self.visit_count == 1:
            return self.visit_ids._fs_form_action()
        action = self.env['ir.actions.act_window']._for_xml_id(
            '369ai_fix.action_service_visit')
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'default_order_id': self.id}
        return action

    # ------------------------------------------------------------------
    # Job card created from this order: hand it to the visit
    # ------------------------------------------------------------------
    def _on_job_card_created(self, job_card):
        res = super()._on_job_card_created(job_card)
        for order in self.sudo():
            for visit in order.visit_ids.filtered(lambda v: v.state not in ('done', 'cancelled')):
                vals = {'job_card_id': job_card.id}
                if not visit.technician_id and job_card.assigned_to:
                    vals['technician_id'] = job_card.assigned_to.id
                if not visit.partner_id and job_card.partner_id:
                    vals['partner_id'] = job_card.partner_id.id
                visit.write(vals)
        return res

    # ------------------------------------------------------------------
    # Website "My orders": add the visit
    # ------------------------------------------------------------------
    @api.model
    def customer_orders(self, host, phone):
        result = super().customer_orders(host, phone)
        if not (isinstance(result, dict) and result.get('ok') and result.get('orders')):
            return result
        site = self.env['online.service.site']._for_host(host)
        refs = [row.get('ref') for row in result['orders']]
        orders = self.sudo().search([('site_id', '=', site.id), ('name', 'in', refs)])
        by_ref = {order.name: order for order in orders}
        for row in result['orders']:
            order = by_ref.get(row.get('ref'))
            visit = order._fs_current_visit() if order else None
            row['visit'] = visit._fs_track_block() if visit else None
        return result
