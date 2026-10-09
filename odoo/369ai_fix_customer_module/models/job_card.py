# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class JobCard(models.Model):
    """Only adds a link to the website order. Job cards made in the shop have
    no link, so for them nothing here does anything."""
    _inherit = 'job.card'

    online_order_id = fields.Many2one('online.service.order', string='Website Order',
                                      copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        cards = super().create(vals_list)
        for card in cards.filtered('online_order_id'):
            try:
                card.online_order_id._on_job_card_created(card)
            except Exception:  # noqa: BLE001 - never block the job card itself
                _logger.exception("Online Service: linking %s to its website order failed", card.name)
        return cards

    def write(self, vals):
        before = {card.id: card.state for card in self} if 'state' in vals else {}
        res = super().write(vals)
        if before:
            for card in self.filtered('online_order_id'):
                if card.state != before.get(card.id):
                    try:
                        card.online_order_id._on_job_card_state(card.state)
                    except Exception:  # noqa: BLE001
                        _logger.exception("Online Service: status update for %s failed", card.name)
        return res
