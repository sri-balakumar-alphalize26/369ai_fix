from odoo import fields, models


class DeviceBrand(models.Model):
    """The brand's warranty check, for the technician only (Catalogue > Brands): "Before you start"
    shows it as a "Check warranty" button. Customers are never sent to the brand."""
    _inherit = 'device.brand'

    fix_warranty_url = fields.Char(
        'Warranty check link',
        help="The brand's own warranty check page (e.g. Apple's Check Coverage). The technician opens it "
             "at the door with the device's IMEI or serial (dial *#06#).")
