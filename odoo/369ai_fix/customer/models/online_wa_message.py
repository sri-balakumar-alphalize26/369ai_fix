# -*- coding: utf-8 -*-
"""Every WhatsApp message to a customer or a technician, kept as sent.

The Booking Desk shows them on the booking's WhatsApp tab, so the office reads exactly what
the customer and the technician got - links included - even while WhatsApp is not
connected (then they wait as "queued"). Login codes are not kept.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

STATUSES = [
    ('sent', 'Sent'),
    ('queued', 'Waiting: WhatsApp not connected'),
    ('blocked', 'Not sent: blocked'),
    ('error', 'Failed'),
    ('skipped', 'Not sent'),
]
WHO = [('customer', 'Customer'), ('technician', 'Technician')]


class OnlineServiceWaMessage(models.Model):
    _name = 'online.service.wa.message'
    _description = 'WhatsApp message (as sent)'
    _order = 'id desc'

    site_id = fields.Many2one('online.service.site', ondelete='cascade', index=True)
    order_id = fields.Many2one('online.service.order', ondelete='cascade', index=True)
    who = fields.Selection(WHO, default='customer', required=True)
    phone = fields.Char()
    body = fields.Text('Message')
    status = fields.Selection(STATUSES)
    detail = fields.Char()

    @api.model
    def _keep(self, site, phone, text, status, detail='', order=None, who='customer'):
        """Note one message; never raises (sending must not fail because of it)."""
        try:
            with self.env.cr.savepoint():
                self.sudo().create({
                    'site_id': site.id if site else False,
                    'order_id': order.id if order else False,
                    'who': who if who in dict(WHO) else 'customer',
                    'phone': phone or '',
                    'body': text or '',
                    'status': status if status in dict(STATUSES) else 'error',
                    'detail': (detail or '')[:200],
                })
        except Exception:  # noqa: BLE001
            _logger.exception("WhatsApp message for %s not kept", order and order.name)

    def _desk_rows(self):
        statuses, who = dict(STATUSES), dict(WHO)
        return [{
            'id': m.id,
            'who': m.who,
            'who_label': who.get(m.who, ''),
            'phone': m.phone or '',
            'body': m.body or '',
            'status': m.status or '',
            'status_label': statuses.get(m.status, ''),
            'at': fields.Datetime.to_string(m.create_date),
        } for m in self]
