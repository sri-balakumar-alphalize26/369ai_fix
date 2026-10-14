from odoo import _, api, models


class JobCard(models.Model):
    _inherit = 'job.card'

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        # Visit fee + quote: a new card starts as a paid inspection (the visit fee),
        # unless the caller chose the inspection type itself.
        if 'inspection_type' in fields_list and not self.env.context.get('default_inspection_type'):
            company = self.env['res.company'].browse(vals['company_id']) if vals.get('company_id') else self.env.company
            if company.repair_visit_fee_mode:
                vals['inspection_type'] = 'paid'
        return vals

    def _visit_fee_product(self):
        param = self.env['ir.config_parameter'].sudo().get_param('mobile_repair.inspection_charge_product_id')
        if not param or not str(param).isdigit():
            return self.env['product.product']
        return self.env['product.product'].browse(int(param)).exists()

    def action_create_quotation(self):
        """Visit fee + quote. A repair on the card: the customer approved, the visit fee is
        included in the repair price. Only the visit fee as a line: the customer declined and
        the fee is billed through that line. Either way the paid inspection is not added on top."""
        for card in self.filtered(lambda c: c.company_id.repair_visit_fee_mode and c.inspection_type == 'paid'):
            fee = card._visit_fee_product()
            repairs = card.service_line_ids.filtered(lambda l: l.product_id != fee)
            if repairs:
                card.inspection_type = 'free'
                card.message_post(body=_('Repair approved: the visit fee is included, not charged on top.'))
            elif card.service_line_ids:
                card.inspection_type = 'free'
                card.message_post(body=_('Repair declined: only the visit fee is billed.'))
        return super().action_create_quotation()
