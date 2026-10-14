from odoo import fields, models


class JobCardIssueType(models.Model):
    _inherit = 'job.card.issue.type'

    device_category_ids = fields.Many2many(
        'device.category', 'job_card_issue_type_device_category_rel', 'issue_type_id', 'category_id',
        string='Device categories',
        help='Devices this issue applies to. Empty: every device. A job card and the website '
             'only offer the issues of the chosen device category.')
