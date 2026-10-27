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
    ('part_in_stock', 'Part in the office: fixed within N days'),
    ('office_part_wait', 'Device at the office, waiting for the part'),
    ('part_arrived_office', 'Part arrived, device at the office'),
    # a lab check: the customer's OK first, before the technician takes the device
    ('lab_permission', 'Lab check: may we take the device?'),
    ('lab_pickup', 'Lab check approved later: pick a time to collect'),
]


class OnlineServiceMessage(models.Model):
    _inherit = 'online.service.message'

    key = fields.Selection(selection_add=BOOKING_KEYS,
                           ondelete={k: 'cascade' for k, _label in BOOKING_KEYS})
    body = fields.Text(
        help="The message the customer gets. Tap the buttons under the box to add their name, the order number, links and more; \"Customers see\" shows how it reads.")

    @api.model
    def _render(self, key, values):
        """Extra placeholders ({reason}, {estimate}, {slot_url}...) come in through the
        context as `osm_extra`, so callers keep using the customer module's sender."""
        extra = self.env.context.get('osm_extra') or {}
        return super()._render(key, dict(values, **extra) if extra else values)
