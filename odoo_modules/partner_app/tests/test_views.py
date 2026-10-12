from lxml import etree

from odoo.tests import tagged

from .common import PartnerAppCase


@tagged('post_install', '-at_install')
class TestPartnerViews(PartnerAppCase):
    """The office's rider form, the Busy line, and the Partner App menu."""

    def _arch(self, view_type, view=None):
        view_id = self.env.ref(view).id if view else False
        return self.env['sa.delivery.partner'].get_views(
            [(view_id, view_type)])['views'][view_type]['arch']

    def test_form_order(self):
        arch = self._arch('form')
        at = [arch.index('name="%s"' % f) for f in
              ('phone', 'work_type', 'busy_display', 'shop_ids')]
        self.assertEqual(at, sorted(at), "Phone, Works In, Busy, Shops")
        self.assertIn('name="partner_app_works_in"', arch)

    def test_kind_is_hidden(self):
        # Own riders only: the office never sees the choice, and new riders
        # keep the delivery module's default.
        form = etree.fromstring(self._arch('form'))
        self.assertEqual(form.xpath("//field[@name='kind']")[0].get('invisible'),
                         '1')
        rider_list = etree.fromstring(self._arch('list'))
        self.assertEqual(
            rider_list.xpath("//field[@name='kind']")[0].get('column_invisible'),
            '1')
        self.assertNotIn('name="kind"', self._arch(
            'list', 'partner_app.view_partner_app_partner_list'))
        search = self._arch('search', 'partner_app.view_partner_app_partner_search')
        self.assertNotIn('kind', search)
        new = self.env['sa.delivery.partner'].create(
            {'name': 'New Person', 'phone': '96890005557'})
        self.assertEqual(new.kind, 'own')

    def test_busy_display(self):
        self.assertEqual(self.deliverer.busy_display, 'Free')
        self.deliverer.service_job_ref = 'SV/0002'
        self.assertEqual(self.deliverer.busy_display,
                         'On a service visit · SV/0002')
        job = self._new_job(self.both)
        job.sa_action_offer()
        self.both.invalidate_recordset(['busy_display'])
        self.assertEqual(self.both.busy_display, 'On a delivery · %s'
                         % (job.sa_ref_code or job.name))

    def test_menu_opens_the_partners(self):
        menu = self.env.ref('partner_app.menu_partner_app_partners')
        self.assertEqual(menu.parent_id,
                         self.env.ref('partner_app.menu_partner_app_root'))
        action = self.env.ref('partner_app.action_partner_app_partners')
        self.assertEqual(action.res_model, 'sa.delivery.partner')
        self.assertEqual(
            action.view_ids.filtered(lambda v: v.view_mode == 'form').view_id,
            self.env.ref('sales_automation_delivery.view_sa_delivery_partner_form'))
        list_arch = self.env['sa.delivery.partner'].get_views(
            [(self.env.ref('partner_app.view_partner_app_partner_list').id,
              'list')])['views']['list']['arch']
        for name in ('name', 'phone', 'work_type', 'busy_display'):
            self.assertIn('name="%s"' % name, list_arch)
