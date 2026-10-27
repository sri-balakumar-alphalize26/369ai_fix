from odoo import fields, models


class FixLabourJob(models.Model):
    """A fixed price for a labour-only job (Catalogue > Labour Prices): one of the Repair Services,
    e.g. Mobile Service OMR 3. The technician taps it under Labour only; the customer approves it
    before the repair. Its own price - the service's website price is not changed."""
    _name = 'fix.labour.job'
    _description = 'Labour price'
    _order = 'name'

    service_id = fields.Many2one(
        'product.template', 'Service', required=True, ondelete='cascade', index=True,
        domain=[('type', '=', 'service')])
    name = fields.Char(related='service_id.name', store=True)
    price = fields.Float(
        'Price for every device', digits='Product Price',
        help='The price for any device. After saving you can give some device types a price of their own.')
    price_ids = fields.One2many(
        'fix.labour.price', 'job_id', string='Price per device type',
        help='A different price for some device types (e.g. Laptop OMR 8). The others get the price for every device.')
    active = fields.Boolean(default=True)

    _one_per_service = models.Constraint('unique (service_id)', 'This service already has a labour price.')

    def _price_for(self, category):
        """The price for a device type: its own row, else the price for every device."""
        self.ensure_one()
        row = self.price_ids.filtered(lambda r: r.category_id == category)[:1] if category else None
        return row.price if row else self.price


class FixLabourPrice(models.Model):
    """One row of a labour price's "Price per device type" table (e.g. Laptop OMR 8)."""
    _name = 'fix.labour.price'
    _description = 'Labour price for a device type'
    _order = 'category_id'

    job_id = fields.Many2one('fix.labour.job', required=True, ondelete='cascade', index=True)
    category_id = fields.Many2one('device.category', 'Device type', required=True, ondelete='cascade')
    price = fields.Float('Price', digits='Product Price', required=True)

    _one_per_type = models.Constraint('unique (job_id, category_id)',
                                      'A device type has one price per labour job.')
