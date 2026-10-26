# -*- coding: utf-8 -*-
"""Spin & Win on the booking: the signed-in customer's prize goes on the order they make
(the cart sends the win's id, or the code typed in the coupon box), the win is used, and the
prize is on the job card as a free line (or the inspection is free). Off switch: nothing here
runs. A code that cannot be used leaves the booking as it is and says why in its chatter."""
import logging

from odoo import _, api, fields, models

from ...customer.models.online_order import clip
from .spin_win import _int

_logger = logging.getLogger(__name__)


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    spin_win_id = fields.Many2one('fix.spin.win', string='Spin & Win prize', readonly=True, copy=False, ondelete='set null')
    spin_prize = fields.Char(related='spin_win_id.prize', string='Prize')
    spin_given = fields.Boolean(compute='_compute_spin_given', string='Prize given')

    @api.depends('spin_win_id.given_on')
    def _compute_spin_given(self):
        for order in self:
            order.spin_given = bool(order.spin_win_id.given_on)

    @api.model
    def website_create(self, payload):
        result = super().website_create(payload)
        if not (isinstance(result, dict) and result.get('ok') and not result.get('duplicate')
                and isinstance(payload, dict)):
            return result
        site = self.env['online.service.site']._for_host(payload.get('host'))
        if not site or not site.wheel_show:
            return result
        Win = self.env['fix.spin.win'].sudo()
        win = Win.browse(_int(payload.get('spin_win_id'))).exists()
        code = clip(payload.get('coupon'), 30).upper()
        if not win and code:
            win = Win.search([('site_id', '=', site.id), ('code', '=', code)], limit=1)
        if not win or win.site_id != site:
            return result
        order = self.sudo().search([('name', '=', result.get('ref')), ('site_id', '=', site.id)], limit=1)
        if not order:
            return result
        partner = self.env['res.partner'].sudo().browse(_int(payload.get('partner_id'))).exists()
        try:
            with self.env.cr.savepoint():
                reason = order._spin_apply(win, partner)
        except Exception:  # noqa: BLE001 - the booking is saved whatever happens to the prize
            _logger.exception("Spin & Win: prize %s on booking %s failed", win.code, order.name)
            reason = _("could not be applied")
        result['spin'] = {'applied': not reason, 'reason': reason, 'prize': win.prize or '', 'code': win.code}
        return result

    def _spin_apply(self, win, partner):
        """The win on this order, the prize on its job card. Returns the reason when refused."""
        self.ensure_one()
        order = self.sudo()
        reason = win._claim(order, partner)
        if reason:
            order.message_post(body=_("Spin & Win code %(code)s (%(prize)s) not applied: %(why)s.",
                                      code=win.code, prize=win.prize or '', why=reason))
            return reason
        order.spin_win_id = win
        order._spin_on_job_cards(win)
        order.message_post(body=_("🎁 Spin & Win prize: %(prize)s (%(code)s).", prize=win.prize or '', code=win.code))
        return ''

    def _spin_on_job_cards(self, win):
        """The prize as a free line on the booking's job card (the first one; one prize, one
        booking), or a free inspection when the prize is the visit itself."""
        self.ensure_one()
        cards = self.sudo().job_card_ids.filtered(lambda c: c.state != 'cancelled').sorted('id')
        if not cards:
            return
        card = cards[0]
        item = win.item_id
        if item.free_visit and 'inspection_type' in card._fields:
            card.inspection_type = 'free'
        product = self.env['fix.service.visit']._vr_labour_product(card.company_id)
        self.env['job.card.service.line'].sudo().create({
            'job_card_id': card.id, 'product_id': product.id,
            'description': _("%s — Spin & Win prize", win.prize or _("Prize")),
            'quantity': 1.0, 'unit_price': 0.0,
            'tax_ids': [(6, 0, product.taxes_id.filtered(lambda t: t.company_id == card.company_id).ids)],
        })
        card.message_post(body=_("🎁 Spin & Win prize: %(prize)s (%(code)s), free.", prize=win.prize or '', code=win.code))

    def action_spin_given(self):
        for order in self:
            if order.spin_win_id:
                order.spin_win_id.action_mark_given()
        return True
