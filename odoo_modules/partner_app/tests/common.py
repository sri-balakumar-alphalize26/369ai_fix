"""Fixtures: three people (Delivery, Service, Both), a shop, and a job.

WhatsApp is kept out of it at `stock.picking._sa_session`, which hands back a
fake session that only remembers who it was asked to message - the tests are
about who gets the offer, not about the message.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase


class _FakeSession:
    def __init__(self, sent):
        self.sent = sent

    def send_message(self, phone, text):
        self.sent.append(phone)
        return True


class PartnerAppCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.sent = []
        fake = _FakeSession(cls.sent)
        Picking = env.registry['stock.picking']
        Guard = env.registry['sa.outbox.guard']
        for patcher in (
            patch.object(Picking, '_sa_session', lambda self: fake),
            # The real guard commits on its own connection; a test must not.
            patch.object(Guard, 'claim', lambda self, key, seconds=60: True),
            patch.object(Guard, 'release', lambda self, key: True),
        ):
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        # With the store module the offer waits for the shop to pack; these
        # tests are about who is offered, so the shop step is skipped.
        settings = env['sa.delivery.settings'].sudo().get_settings()
        if 'shop_confirms' in settings._fields:
            settings.shop_confirms = False

        cls.warehouse = env['stock.warehouse'].search(
            [('company_id', '=', env.company.id)], limit=1)
        cls.shop = env['sa.delivery.shop'].sudo().create({
            'name': 'Partner App Test Counter',
            'phone': '96890005551',
            'warehouse_id': cls.warehouse.id,
        })
        cls.product = env['product.product'].create({
            'name': 'Partner App Test Parcel', 'type': 'consu',
        })
        cls.customer = env['res.partner'].create({
            'name': 'Partner App Customer', 'phone': '+96890005552',
        })

        Rider = env['sa.delivery.partner'].sudo()
        # Riders already in the database must not win the pick.
        Rider.search([]).write({'on_duty': False})
        cls.deliverer = Rider.create({
            'name': 'Delivery Person', 'phone': '96890005553', 'kind': 'own',
            'sequence': 1, 'on_duty': True})
        cls.servicer = Rider.create({
            'name': 'Service Person', 'phone': '96890005554', 'kind': 'own',
            'sequence': 0, 'on_duty': True, 'work_type': 'service'})
        cls.both = Rider.create({
            'name': 'Both Person', 'phone': '96890005555', 'kind': 'own',
            'sequence': 2, 'on_duty': True, 'work_type': 'both'})

    def setUp(self):
        super().setUp()
        self.sent.clear()

    def _new_job(self, rider=None, state='to_assign'):
        customers = self.env.ref('stock.stock_location_customers')
        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': customers.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'location_id': self.warehouse.lot_stock_id.id,
                'location_dest_id': customers.id,
            })],
        })
        picking.action_confirm()
        picking._sa_ensure_identity()
        picking.write({
            'sa_shop_id': self.shop.id,
            'sa_delivery_partner_id': rider.id if rider else False,
            'sa_delivery_state': state,
        })
        return picking
