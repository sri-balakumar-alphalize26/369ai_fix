# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUS_KEYS = [
    ('received', 'Order received'),
    ('confirmed', 'Order confirmed'),
    ('inspection', 'Job card: In Inspection'),
    ('quotation', 'Job card: Quotation'),
    ('repair', 'Job card: Repair'),
    ('completed', 'Job card: Completed'),
    ('done', 'Order done'),
    ('cancelled', 'Cancelled'),
]


class _SafeDict(dict):
    """format_map helper: an unknown {placeholder} stays as typed instead of crashing."""

    def __missing__(self, key):
        return '{' + key + '}'


class OnlineServiceMessage(models.Model):
    """The WhatsApp text sent to the customer at one status."""
    _name = 'online.service.message'
    _description = 'Online Service Status Message'
    _order = 'sequence, id'

    key = fields.Selection(STATUS_KEYS, string='Status', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    body = fields.Text(
        'Message', required=True,
        help="Placeholders: {name} customer, {order} order no., {status}, {job_card} job card no., "
             "{site} website name, {track_url} tracking link, {summary} what was booked.")

    _key_unique = models.Constraint('unique(key)', 'One message per status.')

    @api.model
    def _render(self, key, values):
        """The text for this status, or '' when that message is switched off."""
        msg = self.sudo().search([('key', '=', key)], limit=1)
        if not msg:
            return ''
        try:
            return msg.body.format_map(_SafeDict(values)).strip()
        except (ValueError, IndexError):
            # A stray single brace typed by staff: send the text as it is.
            return msg.body.strip()
