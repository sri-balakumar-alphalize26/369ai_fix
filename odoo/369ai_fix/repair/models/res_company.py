from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    repair_visit_fee_mode = fields.Boolean(
        string='Visit fee + quote',
        help='New job cards start as a Paid Inspection: the customer pays the visit fee '
             '(the Inspection Charge Product) and the technician quotes after inspection. '
             'The fee is waived when the quotation includes a repair.')
