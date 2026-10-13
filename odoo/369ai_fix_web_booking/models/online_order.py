# -*- coding: utf-8 -*-
"""Website bookings against Odoo's own catalogue, and the job cards they make.

The website server calls these through /json/2 with the Online Service bot key
(same door as `website_create`): `website_catalog` to draw the booking wizard,
`website_create` to book, `website_attach` to send the photos and video.
"""
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

UPLOAD_MINUTES = 30
MAX_PHOTOS = 5
MAX_VIDEOS = 1
PHOTO_BYTES = 5 * 1024 * 1024
VIDEO_BYTES = 30 * 1024 * 1024


def _clip(value, size):
    return '' if value in (None, False) else str(value).strip()[:size]


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sniff(data):
    """'image' / 'video' / '' from the file's first bytes - the mimetype a browser
    sends is not trusted."""
    head = data[:16]
    if head.startswith(b'\xff\xd8\xff') or head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image'
    if head[4:8] == b'ftyp':
        brand = head[8:12]
        if brand in (b'heic', b'heix', b'mif1', b'msf1', b'hevc'):
            return 'image'
        return 'video'          # mp4 / mov / m4v / 3gp
    if head[:4] == b'\x1a\x45\xdf\xa3':
        return 'video'          # webm / mkv
    return ''


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    problem = fields.Text('Customer says', help="The customer's own words about the problem.")
    address_partner_id = fields.Many2one('res.partner', string='Booked address', readonly=True,
                                         help="The saved address the customer chose (369 Mart address book).")
    job_card_ids = fields.One2many('job.card', 'online_order_id', string='Job cards')
    job_card_count = fields.Integer(compute='_compute_job_card_count')
    upload_token_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    upload_until = fields.Datetime(readonly=True, copy=False)
    photo_count = fields.Integer('Photos', readonly=True, copy=False)
    video_count = fields.Integer('Videos', readonly=True, copy=False)

    @api.depends('job_card_ids')
    def _compute_job_card_count(self):
        for order in self:
            order.job_card_count = len(order.job_card_ids)

    # ------------------------------------------------------------------
    # Catalogue for the booking wizard
    # ------------------------------------------------------------------
    @api.model
    def website_catalog(self, host):
        """Device tree and repair services, as the website's wizard draws them."""
        self._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        if not site:
            return {'ok': False, 'error': 'unknown website'}
        env = self.sudo().env
        Product = env['product.product'].with_company(site.company_id)
        services = Product.search([('type', '=', 'service'), ('sale_ok', '=', True),
                                   ('repair_category_ids', '!=', False)])
        issues = env['job.card.issue.type'].search([])
        categories = []
        for cat in env['device.category'].search([], order='name'):
            brands = []
            for brand in cat.brand_ids.sorted('name'):
                series = [{'id': s.id, 'name': s.name,
                           'models': [{'id': m.id, 'name': m.name} for m in s.model_ids.sorted('name')]}
                          for s in brand.series_ids.sorted('name')]
                brands.append({'id': brand.id, 'name': brand.name, 'series': series})
            mine = services.filtered(lambda p, c=cat: c in p.repair_category_ids)
            categories.append({
                'id': cat.id,
                'name': cat.name,
                'brands': brands,
                'services': [{
                    'id': p.id,
                    'name': p.name,
                    'price': p.lst_price,
                    'issue_type_ids': p.repair_issue_type_ids.ids,
                    'brand_id': p.device_brand_id.id or False,
                    'series_id': p.device_series_id.id or False,
                    'model_id': p.device_model_id.id or False,
                } for p in mine.sorted(lambda p: (bool(p.device_model_id), p.name))],
                'issue_types': [{'id': i.id, 'name': i.name}
                                for i in issues.filtered(lambda i, c=cat: not i.device_category_ids
                                                         or c in i.device_category_ids)],
            })
        return {'ok': True, 'site': site.name, 'currency': site.company_id.currency_id.name,
                'categories': categories}

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------
    @api.model
    def _wb_device(self, raw):
        """The device ids of one booking line, kept only where they belong together.
        Returns (values for the line, the product or empty)."""
        env = self.sudo().env
        cat = env['device.category'].browse(_int(raw.get('category_id'))).exists()
        brand = env['device.brand'].browse(_int(raw.get('brand_id'))).exists()
        series = env['device.series'].browse(_int(raw.get('series_id'))).exists()
        model = env['device.model'].browse(_int(raw.get('model_id'))).exists()
        if model and (not series or model.series_id != series):
            series = model.series_id
        if series and (not brand or series.brand_id != brand):
            brand = series.brand_id
        if brand and cat and brand.category_id != cat:
            # A model from another category: keep the category, drop the device.
            brand = env['device.brand'].browse()
            series = env['device.series'].browse()
            model = env['device.model'].browse()
        if brand and not cat:
            cat = brand.category_id
        product = env['product.product'].browse(_int(raw.get('product_id'))).exists()
        if product and not product._wb_offered_for(cat, brand, series, model):
            product = env['product.product'].browse()
        return {
            'category_id': cat.id or False,
            'brand_id': brand.id or False,
            'series_id': series.id or False,
            'model_id': model.id or False,
            'product_id': product.id or False,
        }, product

    @api.model
    def _wb_account(self, payload):
        """The signed-in customer and the saved address they chose (ids from the
        website server, which checked the customer's session). The address must be
        theirs: their own contact or one of its child addresses."""
        Partner = self.env['res.partner'].sudo()
        partner = Partner.browse(_int(payload.get('partner_id'))).exists()
        address = Partner.browse(_int(payload.get('address_id'))).exists()
        if not partner:
            return Partner, Partner
        if address and address != partner and address.parent_id != partner.commercial_partner_id \
                and address.parent_id != partner:
            address = Partner
        return partner, address or partner

    @api.model
    def website_create(self, payload):
        p = dict(payload) if isinstance(payload, dict) else {}
        partner, address = self._wb_account(p)
        if address:
            # The order shows what the technician needs, taken from the saved address.
            p['name'] = address.name or partner.name or p.get('name')
            p['phone'] = address.phone or partner.phone or p.get('phone')
            p.setdefault('email', partner.email or '')
            p['area'] = address.street2 or address.city or p.get('area')
            p['address'] = ', '.join(x for x in (address.street, address.street2, address.city,
                                                 address.zip and 'PC %s' % address.zip,
                                                 getattr(address, 'mart369_landmark', '') or '') if x)
            if address.partner_latitude and address.partner_longitude:
                p.setdefault('lat', address.partner_latitude)
                p.setdefault('lng', address.partner_longitude)
        # Lines booked by id get their text from the records, so the order still
        # reads well and older screens keep working.
        prepared = []
        for raw in (p.get('lines') or [])[:30]:
            if not isinstance(raw, dict):
                continue
            ids, product = self._wb_device(raw)
            line = dict(raw)
            if product and not _clip(line.get('issue'), 120):
                line['issue'] = product.name
            if ids['model_id'] and not _clip(line.get('model'), 80):
                model = self.env['device.model'].sudo().browse(ids['model_id'])
                line['model'] = '%s %s' % (model.brand_id.name, model.name)
            if ids['category_id'] and not _clip(line.get('device'), 80):
                line['device'] = self.env['device.category'].sudo().browse(ids['category_id']).name
            prepared.append((line, ids))
        p['lines'] = [line for line, _ids in prepared]

        result = super().website_create(p)
        if not (isinstance(result, dict) and result.get('ok')) or result.get('duplicate'):
            return result
        site = self.env['online.service.site']._for_host(p.get('host'))
        order = self.sudo().search([('name', '=', result.get('ref')), ('site_id', '=', site.id)], limit=1)
        if not order:
            return result
        # super() kept the lines that have a repair text, in order: line them up.
        kept = [ids for line, ids in prepared if _clip(line.get('issue'), 120)]
        for line, ids in zip(order.line_ids.sorted('id'), kept):
            line.write(ids)
        vals = {'problem': _clip(p.get('problem'), 1000) or False}
        if partner:
            vals['partner_id'] = partner.id
            vals['address_partner_id'] = address.id
        token = secrets.token_urlsafe(24)
        vals.update({'upload_token_hash': hashlib.sha256(token.encode()).hexdigest(),
                     'upload_until': fields.Datetime.now() + timedelta(minutes=UPLOAD_MINUTES)})
        order.write(vals)
        try:
            with self.env.cr.savepoint():
                order._wb_make_job_cards()
        except Exception:  # noqa: BLE001 - the booking is saved whatever happens here
            _logger.exception("Website booking %s: job card not created", order.name)
            order.message_post(body=_("The job card could not be made automatically; use Create Job Card."))
        result['upload_token'] = token
        result['job_cards'] = order.job_card_ids.mapped('name')
        return result

    def _wb_make_job_cards(self):
        """One job card per device booked, already filled. The order stays New: the
        alarm rings and staff review it (approve / reject)."""
        self.ensure_one()
        order = self.sudo()
        groups = {}
        for line in order.line_ids:
            key = (line.category_id.id, line.brand_id.id, line.series_id.id, line.model_id.id,
                   '' if line.model_id else (line.model or ''))
            groups.setdefault(key, order.env['online.service.order.line'])
            groups[key] |= line
        partner = order.partner_id or order._find_or_create_partner()
        company = order.company_id or order.env.company
        placeholder = company._wb_unassigned_employee()
        JobCard = order.env['job.card'].with_company(company).with_context(web_booking_auto=True)
        mode_label = dict(order._fields['mode'].selection).get(order.mode, '')
        for (cat_id, brand_id, series_id, model_id, typed_model), lines in groups.items():
            if not brand_id:
                order.message_post(body=_(
                    "No job card for %(what)s: the customer did not pick a brand. Use Create Job Card.",
                    what=', '.join(lines.mapped('issue'))))
                continue
            products = lines.mapped('product_id')
            issue_text = []
            if order.problem:
                issue_text.append(order.problem)
            if typed_model:
                issue_text.append(_("Model (typed by the customer): %s", typed_model))
            missing = lines.filtered(lambda l: not l.product_id)
            if missing:
                issue_text.append(_("Also asked for: %s", ', '.join(missing.mapped('issue'))))
            issue_text.append(_("Website order %(order)s (%(mode)s)", order=order.name, mode=mode_label))
            service_lines = [(0, 0, {
                'product_id': line.product_id.id,
                'description': line.product_id.name,
                'quantity': line.qty or 1,
                'unit_price': line.product_id.lst_price,
                'tax_ids': [(6, 0, line.product_id.taxes_id.filtered(
                    lambda t: t.company_id == order.company_id).ids)],
            }) for line in lines.filtered('product_id')]
            JobCard.create({
                'partner_id': partner.id,
                'company_id': company.id,
                # mobile_repair requires a technician; staff pick the real one on approval.
                'assigned_to': placeholder.id,
                'delivery_type': 'door_step',
                'device_category_id': cat_id or False,
                'brand_id': brand_id,
                'series_id': series_id or False,
                'model_id': model_id or False,
                'issue_type_ids': [(6, 0, products.mapped('repair_issue_type_ids').ids)],
                'issue': '\n'.join(issue_text),
                'service_line_ids': service_lines,
                'online_order_id': order.id,
            })

    def _on_job_card_created(self, job_card):
        """A job card made by the booking itself only links to the order: the order
        stays New (alarm) until staff approve it."""
        if self.env.context.get('web_booking_auto'):
            for order in self.sudo():
                if not order.job_card_id:
                    order.job_card_id = job_card
            return None
        return super()._on_job_card_created(job_card)

    # ------------------------------------------------------------------
    # Photos and video, sent right after the booking
    # ------------------------------------------------------------------
    @api.model
    def website_attach(self, host, ref, token, files):
        """Attach the customer's photos (max 5) and video (max 1) to the booking's job
        card(s). `files`: [{name, data (base64)}]. Allowed for 30 minutes after booking,
        with the token `website_create` returned."""
        self._check_website_caller()
        site = self.env['online.service.site']._for_host(host)
        order = self.sudo().search([('name', '=', _clip(ref, 30)), ('site_id', '=', site.id)],
                                   limit=1) if site else self.sudo().browse()
        if not order or not token or not order.upload_token_hash:
            return {'ok': False, 'error': 'unknown booking'}
        if not hmac.compare_digest(order.upload_token_hash, hashlib.sha256(str(token).encode()).hexdigest()):
            return {'ok': False, 'error': 'bad token'}
        if not order.upload_until or order.upload_until < fields.Datetime.now():
            return {'ok': False, 'error': 'expired'}
        photos, videos = order.photo_count, order.video_count
        decoded = []
        for f in (files or [])[:MAX_PHOTOS + MAX_VIDEOS]:
            try:
                data = base64.b64decode((f or {}).get('data') or '', validate=True)
            except (ValueError, TypeError):
                return {'ok': False, 'error': 'bad file'}
            kind = _sniff(data)
            if kind == 'image':
                photos += 1
                if photos > MAX_PHOTOS or len(data) > PHOTO_BYTES:
                    return {'ok': False, 'error': 'too many or too large photos'}
            elif kind == 'video':
                videos += 1
                if videos > MAX_VIDEOS or len(data) > VIDEO_BYTES:
                    return {'ok': False, 'error': 'too many or too large videos'}
            else:
                return {'ok': False, 'error': 'not a photo or video'}
            decoded.append((kind, _clip(f.get('name'), 80) or kind, data))
        if not decoded:
            return {'ok': True, 'photos': order.photo_count, 'videos': order.video_count}
        target = order.job_card_ids[:1] or order
        Attachment = self.env['ir.attachment'].sudo()
        attachments = Attachment.browse()
        for kind, name, data in decoded:
            attachments |= Attachment.create({
                'name': name,
                'raw': data,
                'res_model': target._name,
                'res_id': target.id,
            })
        order.write({'photo_count': photos, 'video_count': videos})
        body = _("Customer sent %(photos)s photo(s) and %(videos)s video(s) with the booking.",
                 photos=sum(1 for k, _n, _d in decoded if k == 'image'),
                 videos=sum(1 for k, _n, _d in decoded if k == 'video'))
        target.message_post(body=body, attachment_ids=attachments.ids)
        for card in order.job_card_ids[1:]:
            card.message_post(body=body + ' ' + _("(see job card %s)", target.name))
        if target != order:
            order.message_post(body=body + ' ' + _("(on job card %s)", target.name))
        return {'ok': True, 'photos': photos, 'videos': videos}

    def action_view_job_cards(self):
        self.ensure_one()
        cards = self.job_card_ids
        action = {'type': 'ir.actions.act_window', 'res_model': 'job.card', 'name': _("Job cards")}
        if len(cards) == 1:
            action.update(view_mode='form', res_id=cards.id)
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', cards.ids)])
        return action


class OnlineServiceOrderLine(models.Model):
    _inherit = 'online.service.order.line'

    category_id = fields.Many2one('device.category', string='Device category')
    brand_id = fields.Many2one('device.brand', string='Brand')
    series_id = fields.Many2one('device.series', string='Series')
    model_id = fields.Many2one('device.model', string='Model ')
    product_id = fields.Many2one('product.product', string='Repair service')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _wb_offered_for(self, category, brand, series, model):
        """Same rule as the job card's Required Services list: each of the service's
        category / brand / series / model is empty or matches the device."""
        self.ensure_one()
        if self.type != 'service' or not self.sale_ok:
            return False
        checks = (
            (self.repair_category_ids, category, lambda: category in self.repair_category_ids),
            (self.device_brand_id, brand, lambda: self.device_brand_id == brand),
            (self.device_series_id, series, lambda: self.device_series_id == series),
            (self.device_model_id, model, lambda: self.device_model_id == model),
        )
        return all(not value or (device and same()) for value, device, same in checks)
