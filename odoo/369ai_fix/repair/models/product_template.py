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
        string='Problems it fixes',
        help='Faults this repair or part fixes. A booking for a repair fills the job card\'s Issue Types; '
             'at the visit the technician ticks the problems found and is offered the parts that fix them.')
    # for spare parts: kept apart from repair_category_ids, which marks the website's repairs
    fit_category_ids = fields.Many2many(
        'device.category', 'product_template_fit_category_rel', 'product_tmpl_id', 'category_id',
        string='Fits device types',
        help='Spare parts: the device types this part fits. At the visit it is only offered for those '
             '(empty: any device).')
    fix_part_grade = fields.Selection(
        [('original', 'Original'), ('compatible', 'Compatible'), ('refurbished', 'Refurbished')],
        string='Grade',
        help='Spare parts: the brand\'s original part, a compatible copy or a refurbished one. At the visit '
             'the technician can offer two grades of the same part, and the customer chooses one.')
