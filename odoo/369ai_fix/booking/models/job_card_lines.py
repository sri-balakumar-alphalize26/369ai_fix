from odoo import fields, models


class JobCardSparePartLine(models.Model):
    _inherit = 'job.card.spare.part.line'

    wb_on_hand = fields.Float('On hand', related='product_id.qty_available',
                              help="In stock now. 0 or less: the part must be ordered.")


class JobCard(models.Model):
    _inherit = 'job.card'

    def action_wb_call(self):
        """Call the customer of the website booking (Main / Alternative)."""
        self.ensure_one()
        if self.online_order_id:
            return self.online_order_id.action_wb_call()
        return self.env['online.service.order']._wb_tel(self.phone or self.partner_id.phone or '')
