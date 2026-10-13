from odoo import api, fields, models

BOOKING_KEYS = [
    ('approved', 'Booking approved (all parts in stock)'),
    ('approved_order', 'Booking approved (a part must be ordered)'),
    ('rejected', 'Booking rejected'),
    ('parts_declined', 'Customer declined ordering the parts'),
    ('parts_ordering', 'Customer said yes: ordering the parts'),
    ('part_ordered', 'Part ordered'),
    ('part_delayed', 'Part delayed'),
    ('part_arrived', 'All parts arrived'),
    ('slot_booked', 'Time slot booked'),
    ('quote_changed', 'New price to approve'),
    ('office_taken', 'Device taken to the office'),
    ('return_ready', 'Pick a time to bring the device back'),
]


class OnlineServiceMessage(models.Model):
    _inherit = 'online.service.message'

    key = fields.Selection(selection_add=BOOKING_KEYS,
                           ondelete={k: 'cascade' for k, _label in BOOKING_KEYS})
    body = fields.Text(
        help="Placeholders: {name} customer, {order} order no., {status}, {job_card} job card no., "
             "{site} website name, {track_url} tracking link, {summary} what was booked. "
             "Booking messages also have {estimate} (repairs, parts and total), {slot_url} (link to pick "
             "a time), {reason}, {parts}, {part}, {days}, {date} and {slot}.")

    @api.model
    def _render(self, key, values):
        """Extra placeholders ({reason}, {estimate}, {slot_url}...) come in through the
        context as `osm_extra`, so callers keep using the customer module's sender."""
        extra = self.env.context.get('osm_extra') or {}
        return super()._render(key, dict(values, **extra) if extra else values)
