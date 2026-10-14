# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

DRAWING_KEYS = ('3d', 'line', 'flat', 'sketch', 'duotone')


class OnlineServiceSite(models.Model):
    _inherit = 'online.service.site'

    show_device_photos = fields.Boolean(
        'Show real photos on the website',
        help="On: device types (Mobile Phones, Laptops…) show their chosen photo. "
             "Off: they show their drawing sketch. Both stay saved, so you can switch any time.")
    drawing_style = fields.Selection(
        [('3d', '3D'), ('line', 'Line'), ('flat', 'Flat'), ('sketch', 'Sketch'), ('duotone', 'Duotone')],
        string='Drawing style', default='3d', required=True,
        help="Which of the 5 drawing styles every device type uses when real photos are off.")
    # Every device type, for the Device Pictures screen (switch at the top, device types below).
    fix_device_category_ids = fields.Many2many('device.category', string='Device types',
                                               compute='_compute_fix_device_category_ids')

    def _compute_fix_device_category_ids(self):
        categories = self.env['device.category'].search([])
        for site in self:
            site.fix_device_category_ids = categories

    @api.model
    def action_fix_device_pictures(self):
        """Menu Device Pictures: the website's switch with all device types below. One website
        opens straight away; with several, pick the website first."""
        sites = self.search([('active', '=', True)])
        view = self.env.ref('369ai_fix.view_online_site_device_pictures_form')
        action = {
            'type': 'ir.actions.act_window',
            'name': self.env._('Device Pictures'),
            'res_model': 'online.service.site',
            'target': 'current',
        }
        if len(sites) == 1:
            action.update(res_id=sites.id, view_mode='form', views=[(view.id, 'form')])
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', sites.ids)],
                          views=[(False, 'list'), (view.id, 'form')])
        return action

    # ------------------------------------------------------------------
    # Device Pictures screen (OWL client action 369ai_fix.device_pictures)
    # ------------------------------------------------------------------
    def _fix_check_editor(self):
        if not self.env.user.has_group('369ai_fix.group_fix_website_editor'):
            raise AccessError(self.env._("Only website editors can change the website's pictures."))

    @api.model
    def fix_device_pictures_data(self, site_id=False):
        """Everything the Device Pictures screen draws: the websites, the chosen look and style
        of one website, and every device type with its 5 drawings and its photos."""
        self._fix_check_editor()
        sites = self.search([('active', '=', True)])
        site = sites.filtered(lambda s: s.id == site_id)[:1] or sites[:1]
        devices = []
        for cat in self.env['device.category'].search([], order='name'):
            devices.append({
                'id': cat.id,
                'name': cat.name,
                'drawings': {key: cat._fix_drawing_url(key) for key in DRAWING_KEYS},
                'photos': [{
                    'id': img.id,
                    'name': img.name,
                    'url': img._web_url('image_512'),
                    'shown': img == cat.web_photo_id,
                } for img in cat.web_photo_ids],
            })
        return {
            'sites': [{'id': s.id, 'name': s.name} for s in sites],
            'site_id': site.id or False,
            'mode': 'photo' if site.show_device_photos else 'drawing',
            'style': site.drawing_style or '3d',
            'styles': [{'key': k, 'name': n} for k, n in self._fields['drawing_style'].selection],
            'devices': devices,
            'device_form_view_id': self.env.ref('369ai_fix.view_device_category_pictures_form').id,
        }

    @api.model
    def fix_device_pictures_save(self, site_id, payload):
        """One choice from the Device Pictures screen, saved straight away:
        {'mode': 'drawing'|'photo'}, {'style': '3d'|…} or {'device_id': …, 'photo_id': …}."""
        self._fix_check_editor()
        site = self.browse(site_id).exists()
        if not site:
            raise UserError(self.env._("This website no longer exists."))
        payload = payload or {}
        if payload.get('mode') in ('drawing', 'photo'):
            site.show_device_photos = payload['mode'] == 'photo'
        if payload.get('style'):
            if payload['style'] not in DRAWING_KEYS:
                raise UserError(self.env._("Unknown drawing style."))
            site.drawing_style = payload['style']
        if payload.get('photo_id'):
            image = self.env['fix.web.image'].browse(int(payload['photo_id'])).exists()
            if not image or image.category_id.id != int(payload.get('device_id') or 0):
                raise UserError(self.env._("This photo doesn't belong to that device type."))
            image.action_show()
        return {'ok': True, 'mode': 'photo' if site.show_device_photos else 'drawing', 'style': site.drawing_style}

    def action_fix_load_starter_pictures(self):
        """Fill empty picture places from the starter set; chosen pictures are kept."""
        from ..hooks import load_starter_pictures
        services, logos = load_starter_pictures(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Starter pictures'),
                'message': self.env._('%(s)s service photos and %(l)s brand logos added.', s=services, l=logos),
                'type': 'success',
            },
        }
