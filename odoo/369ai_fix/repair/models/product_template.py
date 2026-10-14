from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    repair_category_ids = fields.Many2many(
        'device.category', 'product_template_repair_category_rel', 'product_tmpl_id', 'category_id',
        string='Device categories',
        help='Devices this service is offered for. On a job card, Required Services lists a service '
             'when its categories include the card\'s device category (or are empty), and its '
             'Brand / Series / Model match the card (or are empty).')
    repair_issue_type_ids = fields.Many2many(
        'job.card.issue.type', 'product_template_repair_issue_rel', 'product_tmpl_id', 'issue_type_id',
        string='Issue types',
        help='Faults this service fixes. A booking for this service fills the job card\'s Issue Types.')
