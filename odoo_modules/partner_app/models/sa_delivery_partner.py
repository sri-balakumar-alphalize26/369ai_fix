"""Who works in which line - Delivery, Service or both - and who is busy.

The delivery module knows riders. The partner app now also carries service
agents (on-site repair and install), and some people do both. They are all
the same `sa.delivery.partner` record with the same login; `work_type` says
which lines they work in. `kind` is untouched and still only decides pay.

**Busy** is one state across both lines. Somebody holding a delivery job,
even one only offered, is busy on delivery; somebody out on a service visit
is busy on service. A person busy on one line is offered nothing from the
other until the job in hand ends.

The service side writes `service_job_ref` when an agent accepts a visit and
clears it when the visit ends. Until the service module is on the database
nothing writes it, so nobody is ever busy on service.
"""

from odoo import api, fields, models
from odoo.fields import Domain

# A delivery job in the rider's hands. `offered` counts: someone holding a
# delivery offer must not be offered a service visit at the same time.
DELIVERY_BUSY = ('offered', 'accepted', 'picked', 'dispatched',
                 'out_for_delivery', 'returning')

# The service module's job model. None until the senior's module lands; the
# service side switches on by itself once the model is on the database.
SERVICE_JOB_MODEL = None


class SaDeliveryPartner(models.Model):
    _inherit = 'sa.delivery.partner'

    work_type = fields.Selection([
        ('delivery', 'Delivery'),
        ('service', 'Service'),
        ('both', 'Delivery and Service'),
    ], string='Works In', default='delivery', required=True,
        help="Which jobs this person is offered in the partner app. Delivery "
             "only, Service only (on-site repair and install visits), or "
             "both, switching between them in the app.")
    is_test_rider = fields.Boolean(
        'Test rider', copy=False,
        help="For trying the app with a made-up number. Signs in with the "
             "fixed code 111111, no WhatsApp message of any kind is sent to "
             "this number, and until the service module is installed the "
             "app shows the Service side with sample jobs. Leave off for "
             "real people.")
    service_job_ref = fields.Char(
        'Service Visit In Hand', readonly=True, copy=False,
        help="Set when this person accepts a service visit and cleared when "
             "it ends. While set, no delivery is offered to them.")

    busy_line = fields.Selection([
        ('none', 'Free'),
        ('delivery', 'On a delivery'),
        ('service', 'On a service visit'),
    ], string='Busy Line', compute='_compute_busy')
    busy_ref = fields.Char('Busy With', compute='_compute_busy')
    # What the office reads: "Free", or the line and the job, in one line.
    busy_display = fields.Char('Busy', compute='_compute_busy')

    @api.depends('service_job_ref')
    def _compute_busy(self):
        Picking = self.env['stock.picking'].sudo()
        lines = dict(self._fields['busy_line']._description_selection(self.env))
        for rider in self:
            if rider.service_job_ref:
                rider.busy_line = 'service'
                rider.busy_ref = rider.service_job_ref
            else:
                job = Picking.search([
                    ('sa_delivery_partner_id', '=', rider.id),
                    ('sa_delivery_state', 'in', DELIVERY_BUSY),
                ], order='id asc', limit=1)
                rider.busy_line = 'delivery' if job else 'none'
                rider.busy_ref = (job.sa_ref_code or job.name) if job else False
            rider.busy_display = ('%s · %s' % (lines[rider.busy_line], rider.busy_ref)
                                  if rider.busy_ref else lines[rider.busy_line])

    @api.model
    def _partner_app_test_rider_for(self, phone):
        """The test rider this number belongs to, or an empty recordset.

        Matched on the last nine digits, as the delivery module's
        `_sa_by_phone` does, so a number with or without its country code
        is the same number.
        """
        digits = self._sa_digits(phone)
        if len(digits) < 8:
            return self.browse()
        for rider in self.sudo().search([('is_test_rider', '=', True)]):
            mine = self._sa_digits(rider.phone)
            if mine and mine[-9:] == digits[-9:]:
                return rider
        return self.browse()

    # ============================================================ delivery

    @api.model
    def _partner_app_not_for_delivery(self):
        """Who must not be offered a delivery right now."""
        return Domain('work_type', '=', 'service') | Domain(
            'service_job_ref', '!=', False)

    def _partner_app_can_deliver(self):
        self.ensure_one()
        return (self.work_type != 'service'
                and not self.service_job_ref)

    @api.model
    def _search(self, domain, *args, **kwargs):
        """Inside a delivery pick, the people who cannot deliver are not there.

        Only under `partner_app_delivery_pick`, which only
        `_partner_app_pick_for_delivery` sets. Filtering the search rather
        than the result works whichever `_sa_pick_for` ends up running: the
        delivery module's own, or an add-on's that replaces it without
        calling it.
        """
        if self.env.context.get('partner_app_delivery_pick'):
            domain = Domain(domain) & ~self._partner_app_not_for_delivery()
        return super()._search(domain, *args, **kwargs)

    @api.model
    def _partner_app_pick_for_delivery(self, shop):
        """`_sa_pick_for`, minus Service-only people and anyone on a visit.

        Also passed as `rider_rpc_exclude`, which the rider-app add-ons
        already honour - belt and braces for a pick that does not search.
        """
        blocked = self.sudo().with_context(active_test=False).search(
            self._partner_app_not_for_delivery())
        exclude = set(self.env.context.get('rider_rpc_exclude') or [])
        exclude.update(blocked.ids)
        rider = self.with_context(
            partner_app_delivery_pick=True,
            rider_rpc_exclude=sorted(exclude),
        )._sa_pick_for(shop)
        if rider and not rider._partner_app_can_deliver():
            return self.browse()
        return rider

    def _sa_waiting_jobs(self):
        """Clocking on sweeps up waiting deliveries - not for these people."""
        if not self._partner_app_can_deliver():
            return self.env['stock.picking']
        return super()._sa_waiting_jobs()

    # ============================================================= service

    @api.model
    def _partner_app_service_available(self):
        """True once the service module is on this database."""
        return bool(SERVICE_JOB_MODEL and SERVICE_JOB_MODEL in self.env)

    def _partner_app_block(self):
        """What `/api/partner/me` says about this person."""
        self.ensure_one()
        lines = {'delivery': ['delivery'], 'service': ['service'],
                 'both': ['delivery', 'service']}[self.work_type]
        service = self._partner_app_service_available()
        # A test rider sees the Service side before the service module is
        # here, filled by the app's sample jobs, so the switch can be tried.
        preview = bool(self.is_test_rider and not service)
        return {
            'work_type': self.work_type,
            'work_type_label': dict(
                self._fields['work_type']._description_selection(self.env)
            )[self.work_type],
            # The lines the app should open: Service only once the service
            # module is there to give it jobs, or as a test rider's preview.
            'lines': [l for l in lines if l == 'delivery' or service or preview],
            'busy_line': self.busy_line,
            'busy_ref': self.busy_ref or None,
            'service_available': service,
            'service_preview': preview,
        }
