from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    wb_unassigned_employee_id = fields.Many2one(
        'hr.employee', string='Technician placeholder (website)',
        help="Job cards made from website bookings start with this employee, because "
             "IT & Mobile Repair requires a technician; staff choose the real one on approval.")
    wb_slot_days = fields.Integer('Show time slots for the next (days)', default=7)
    wb_slot_lead_hours = fields.Integer('Earliest slot from now (hours)', default=2)
    wb_slot_change_hours = fields.Integer('Customer can change the slot until (hours before)', default=2)
    repair_requote_pct = fields.Float('Ask again when a part costs more than (%)', default=10.0,
                                      help="An ordered part that arrives dearer than this over its estimated "
                                           "cost needs a new price approved by the customer.")

    def _wb_unassigned_employee(self):
        self.ensure_one()
        employee = self.sudo().wb_unassigned_employee_id
        if not employee:
            employee = self.env['hr.employee'].sudo().create({
                'name': _("To be assigned (website)"),
                'company_id': self.id,
            })
            self.sudo().wb_unassigned_employee_id = employee
        return employee


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wb_slot_days = fields.Integer(related='company_id.wb_slot_days', readonly=False)
    wb_slot_lead_hours = fields.Integer(related='company_id.wb_slot_lead_hours', readonly=False)
    wb_slot_change_hours = fields.Integer(related='company_id.wb_slot_change_hours', readonly=False)
    wb_unassigned_employee_id = fields.Many2one(related='company_id.wb_unassigned_employee_id', readonly=False)
    repair_requote_pct = fields.Float(related='company_id.repair_requote_pct', readonly=False)
