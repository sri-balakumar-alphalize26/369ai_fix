from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    repair_visit_fee_mode = fields.Boolean(
        related='company_id.repair_visit_fee_mode', readonly=False)
