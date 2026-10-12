from odoo.tests import tagged

from .common import PartnerAppCase


@tagged('post_install', '-at_install')
class TestRoles(PartnerAppCase):
    """Works In, busy, and who a delivery may be offered to."""

    def test_existing_riders_default_to_delivery(self):
        self.assertEqual(self.deliverer.work_type, 'delivery')
        self.assertEqual(self.deliverer.busy_line, 'none')

    def test_pick_skips_service_only(self):
        # Service Person is first by sequence - the pick must pass over them.
        rider = self.env['sa.delivery.partner']._partner_app_pick_for_delivery(
            self.shop)
        self.assertEqual(rider, self.deliverer)

    def test_pick_skips_anyone_on_a_visit(self):
        self.deliverer.service_job_ref = 'SV/0001'
        self.deliverer.work_type = 'both'
        rider = self.env['sa.delivery.partner']._partner_app_pick_for_delivery(
            self.shop)
        self.assertEqual(rider, self.both)
        self.assertEqual(self.deliverer.busy_line, 'service')
        self.assertEqual(self.deliverer.busy_ref, 'SV/0001')

    def test_pick_nobody_left(self):
        (self.deliverer | self.both).write({'on_duty': False})
        rider = self.env['sa.delivery.partner']._partner_app_pick_for_delivery(
            self.shop)
        self.assertFalse(rider)

    def test_offer_to_service_only_goes_to_someone_who_delivers(self):
        job = self._new_job(self.servicer)
        job.sa_action_offer()
        self.assertEqual(job.sa_delivery_partner_id, self.deliverer)
        self.assertEqual(job.sa_delivery_state, 'offered')
        self.assertEqual(self.sent, [self.deliverer.phone])

    def test_offer_with_nobody_left_goes_back_to_dispatch(self):
        (self.deliverer | self.both).write({'on_duty': False})
        job = self._new_job(self.servicer)
        job.sa_action_offer()
        self.assertFalse(job.sa_delivery_partner_id)
        self.assertEqual(job.sa_delivery_state, 'to_assign')
        self.assertFalse(self.sent)

    def test_offer_to_a_deliverer_is_untouched(self):
        job = self._new_job(self.both)
        job.sa_action_offer()
        self.assertEqual(job.sa_delivery_partner_id, self.both)
        self.assertEqual(job.sa_delivery_state, 'offered')

    def test_delivery_job_makes_busy(self):
        job = self._new_job(self.both)
        job.sa_action_offer()
        self.both.invalidate_recordset(['busy_line', 'busy_ref'])
        self.assertEqual(self.both.busy_line, 'delivery')
        self.assertEqual(self.both.busy_ref, job.sa_ref_code or job.name)

    def test_clock_on_sweeps_nothing_for_service_only(self):
        self._new_job()
        self.assertFalse(self.servicer._sa_waiting_jobs())
        self.assertTrue(self.deliverer._sa_waiting_jobs())

    def test_plain_search_is_not_filtered(self):
        Rider = self.env['sa.delivery.partner'].sudo()
        self.assertIn(self.servicer, Rider.search([('on_duty', '=', True)]))

    def test_block_without_service_module(self):
        block = self.both._partner_app_block()
        self.assertEqual(block['work_type'], 'both')
        self.assertFalse(block['service_available'])
        # No service module: the app opens Delivery only.
        self.assertEqual(block['lines'], ['delivery'])
