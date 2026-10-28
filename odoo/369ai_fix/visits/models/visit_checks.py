# -*- coding: utf-8 -*-
"""Before the technician touches the device: the brand warranty, the safety check and the device photos.

At the door, after "Arrived", the technician first asks about the brand's warranty (a "Check
warranty" link per brand, for the technician only). Under warranty, the customer chooses: our
repair (noted on the job card) or keeping the warranty (the visit closes, nothing touched).
Then the technician ticks what they wear (gloves, mask, ...),
takes 1 to 3 photos of it, photographs the device from every side and records one
short video. "Start work" stays shut until that is done - on the visit form and the
Booking Desk (a "Before you start" window) and on the technician's phone page. A
manager can start anyway with a reason, which is logged.

Both lists are edited under 369 ai Fix > Configuration (Safety Checklist, Device Photos).
"""
import base64

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.image import image_process
from odoo.tools.mimetypes import guess_mimetype

from .service_visit import _iso

MIN_SAFETY_PHOTOS = 1
MAX_SAFETY_PHOTOS = 3
PHOTO_BYTES = 8 * 1024 * 1024
VIDEO_BYTES = 30 * 1024 * 1024
WARRANTY_ANSWERS = [
    ('no', 'Not under warranty'),
    ('ours', 'Under warranty: the customer wants our repair'),
    ('keep', 'Under warranty: the customer keeps the warranty'),
]


def _sniff(data):
    """'image' / 'video' / '' from the file's first bytes - what the phone says is not trusted."""
    head = data[:16]
    if head.startswith(b'\xff\xd8\xff') or head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image'
    if head[4:8] == b'ftyp':
        return 'image' if head[8:12] in (b'heic', b'heix', b'mif1', b'msf1', b'hevc') else 'video'
    if head[:4] == b'\x1a\x45\xdf\xa3':
        return 'video'          # webm / mkv
    return ''


class SafetyItem(models.Model):
    _name = 'fix.safety.item'
    _description = 'Safety checklist item'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    required = fields.Boolean(default=True, help="Work cannot start until this is ticked.")
    active = fields.Boolean(default=True)


class DeviceAngle(models.Model):
    _name = 'fix.device.angle'
    _description = 'Device photo (side)'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    required = fields.Boolean(default=True, help="Work cannot start until this photo is taken.")
    active = fields.Boolean(default=True)


class VisitSafetyLine(models.Model):
    _name = 'fix.visit.safety.line'
    _description = 'Doorstep visit: safety tick'
    _order = 'sequence, id'

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one('fix.safety.item', required=True, ondelete='restrict')
    name = fields.Char(related='item_id.name')
    required = fields.Boolean(related='item_id.required')
    sequence = fields.Integer(related='item_id.sequence', store=True)
    worn = fields.Boolean('Done')
    checked_on = fields.Datetime(readonly=True)

    def write(self, vals):
        if 'worn' in vals:
            vals['checked_on'] = fields.Datetime.now() if vals['worn'] else False
        return super().write(vals)


class VisitCheckPhoto(models.Model):
    _name = 'fix.visit.check.photo'
    _description = 'Doorstep visit: photo before work'
    _order = 'kind, sequence, id'

    visit_id = fields.Many2one('fix.service.visit', required=True, ondelete='cascade', index=True)
    kind = fields.Selection([('safety', 'Safety'), ('device', 'Device'), ('after', 'After repair')],
                            required=True, default='device')
    angle_id = fields.Many2one('fix.device.angle', string='Side', ondelete='restrict')
    name = fields.Char(compute='_compute_name')
    sequence = fields.Integer(related='angle_id.sequence', store=True)
    image = fields.Image('Photo', max_width=1920, max_height=1920)
    taken_on = fields.Datetime(readonly=True)

    @api.depends('kind', 'angle_id')
    def _compute_name(self):
        for photo in self:
            photo.name = (photo.angle_id.name if photo.kind == 'device'
                          else _("After repair") if photo.kind == 'after' else _("Safety photo"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('image'):
                vals['taken_on'] = fields.Datetime.now()
        return super().create(vals_list)

    def write(self, vals):
        if 'image' in vals:
            vals['taken_on'] = fields.Datetime.now() if vals['image'] else False
        return super().write(vals)


class ServiceVisit(models.Model):
    _inherit = 'fix.service.visit'

    warranty_answer = fields.Selection(WARRANTY_ANSWERS, 'Brand warranty', readonly=True, copy=False, tracking=True)
    safety_line_ids = fields.One2many('fix.visit.safety.line', 'visit_id', string='Safety check')
    safety_photo_ids = fields.One2many('fix.visit.check.photo', 'visit_id', string='Safety photos',
                                       domain=[('kind', '=', 'safety')])
    device_photo_ids = fields.One2many('fix.visit.check.photo', 'visit_id', string='Device photos',
                                       domain=[('kind', '=', 'device')])
    device_video = fields.Binary('Device video', attachment=True, copy=False)
    device_video_name = fields.Char(copy=False)
    checks_missing = fields.Text('Still to do', compute='_compute_checks')
    checks_done = fields.Boolean('Checks done', compute='_compute_checks')
    checks_done_on = fields.Datetime('Checks done on', readonly=True, copy=False)
    checks_override_reason = fields.Char('Started without the checks because', copy=False)
    checks_override_by_id = fields.Many2one('res.users', 'Allowed by', readonly=True, copy=False)
    checks_is_manager = fields.Boolean(compute='_compute_checks_is_manager')

    @api.depends('warranty_answer', 'safety_line_ids.worn', 'safety_photo_ids.image', 'device_photo_ids.image',
                 'device_video')
    def _compute_checks(self):
        for visit in self:
            missing = visit._vc_missing()
            visit.checks_missing = '\n'.join(missing)
            visit.checks_done = not missing

    def _compute_checks_is_manager(self):
        manager = self.env.user.has_group('mobile_repair.group_mobile_repair_manager')
        for visit in self:
            visit.checks_is_manager = manager

    # ------------------------------------------------------------------ the lists
    def _vc_prepare(self):
        """One safety line per active item and one photo slot per active side, so the
        window and the phone page show the whole list. Items added later appear too."""
        Items = self.env['fix.safety.item'].sudo().search([])
        Angles = self.env['fix.device.angle'].sudo().search([])
        for visit in self.sudo():
            have = visit.safety_line_ids.item_id
            new = [{'visit_id': visit.id, 'item_id': item.id} for item in Items - have]
            if new:
                self.env['fix.visit.safety.line'].sudo().create(new)
            have = visit.device_photo_ids.angle_id
            new = [{'visit_id': visit.id, 'kind': 'device', 'angle_id': a.id} for a in Angles - have]
            if new:
                self.env['fix.visit.check.photo'].sudo().create(new)

    def _vc_missing(self):
        """What is still to do, in words: [] when work may start."""
        self.ensure_one()
        visit = self.sudo()
        missing = [] if visit.warranty_answer in ('no', 'ours') else [_("Brand warranty not answered")]
        ticked = visit.safety_line_ids.filtered('worn').item_id
        for item in self.env['fix.safety.item'].sudo().search([('required', '=', True)]):
            if item not in ticked:
                missing.append(_("%s not ticked", item.name))
        photos = len(visit.safety_photo_ids.filtered('image'))
        if photos < MIN_SAFETY_PHOTOS:
            missing.append(_("Safety photo missing"))
        elif photos > MAX_SAFETY_PHOTOS:
            missing.append(_("At most %s safety photos", MAX_SAFETY_PHOTOS))
        taken = visit.device_photo_ids.filtered('image').angle_id
        for angle in self.env['fix.device.angle'].sudo().search([('required', '=', True)]):
            if angle not in taken:
                missing.append(_("%s photo missing", angle.name))
        if not visit.device_video:
            missing.append(_("Video missing"))
        return missing

    # ------------------------------------------------------------------ Start work
    def action_start(self):
        """Start work - only once the checks are done. From a form or the desk it opens
        the "Before you start" window instead."""
        if self.env.context.get('fix_checks_passed'):
            return super().action_start()
        self._fs_require(('arrived',))
        todo = self.filtered(lambda v: v._vc_missing())
        if not todo:
            self._vc_stamp()
            return super().action_start()
        if len(self) > 1:
            raise UserError(_("Do the checks before starting: %s", ', '.join(todo.mapped('name'))))
        return self.action_open_checks()

    def action_open_checks(self):
        self.ensure_one()
        self._vc_prepare()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Before you start - %s", self.name),
            'res_model': 'fix.service.visit',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('369ai_fix.view_service_visit_checks_form').id, 'form')],
            'target': 'new',
        }

    def action_start_checked(self):
        """The window's "Start work": the checks must be complete."""
        self.ensure_one()
        self._fs_require(('arrived',))
        missing = self._vc_missing()
        if missing:
            raise UserError(_("Not yet - still to do:\n%s", '\n'.join('• ' + m for m in missing)))
        self._vc_stamp()
        self.with_context(fix_checks_passed=True).action_start()
        return {'type': 'ir.actions.act_window_close'}

    def action_start_without_checks(self):
        """A manager starts anyway; the reason goes on the visit and in the chatter."""
        self.ensure_one()
        if not self.env.user.has_group('mobile_repair.group_mobile_repair_manager'):
            raise AccessError(_("Only a manager can start work without the checks."))
        self._fs_require(('arrived',))
        reason = (self.checks_override_reason or '').strip()
        if not reason:
            raise UserError(_("Write why work starts without the checks."))
        missing = self._vc_missing()
        self.sudo().checks_override_by_id = self.env.user
        self.message_post(body=_("%(who)s started work without the checks: %(reason)s. Not done: %(missing)s.",
                                 who=self.env.user.name, reason=reason,
                                 missing=', '.join(missing) or _("nothing")),
                          subtype_xmlid='mail.mt_note')
        self.with_context(fix_checks_passed=True).action_start()
        return {'type': 'ir.actions.act_window_close'}

    # ------------------------------------------------------------------ the brand's warranty (asked first)
    def _vc_warranty(self, answer):
        """The technician's answer about the brand's warranty. "keep": the customer keeps the
        brand's warranty, so nothing is touched and the visit closes politely, free."""
        self.ensure_one()
        visit = self.sudo()
        self._fs_require(('arrived',))
        if answer not in dict(WARRANTY_ANSWERS):
            raise UserError(_("Choose the answer about the brand's warranty."))
        visit.warranty_answer = answer
        if answer == 'ours':
            body = _("Under the brand's warranty: the customer chose our repair (the brand's warranty may end). "
                     "Noted by %s.", self.env.user.name)
            (visit.job_card_id or visit).message_post(body=body, subtype_xmlid='mail.mt_note')
        elif answer == 'keep':
            if not (visit.check_found or '').strip():
                visit.check_found = _("Your device is still under the brand's warranty and you chose to keep it, "
                                      "so we did not open it.")
            visit._vr_no_repair('warranty')
        return True

    # the "Before you start" window's buttons
    def action_vc_warranty_no(self):
        self._vc_warranty('no')
        return self.action_open_checks()

    def action_vc_warranty_ours(self):
        self._vc_warranty('ours')
        return self.action_open_checks()

    def action_vc_warranty_keep(self):
        self._vc_warranty('keep')
        return {'type': 'ir.actions.act_window_close'}

    def _vc_warranty_view(self):
        self.ensure_one()
        brand = self.sudo()._vr_device()[1]
        return {
            'answer': self.sudo().warranty_answer or '',
            'answers': [{'key': k, 'label': _(label)} for k, label in WARRANTY_ANSWERS],
            'brand': brand.name or '',
            'check_url': brand.fix_warranty_url or '',
        }

    def _vc_stamp(self):
        for visit in self.sudo().filtered(lambda v: not v.checks_done_on):
            visit.checks_done_on = fields.Datetime.now()
            visit.message_post(body=_("Safety check, %(photos)s device photos and the video done before work.",
                                      photos=len(visit.device_photo_ids.filtered('image'))),
                               subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------ what the customer sees
    def _vc_worn(self):
        """The safety items ticked, once the checks are done (empty when started without them)."""
        self.ensure_one()
        visit = self.sudo()
        if not visit.checks_done_on:
            return []
        return visit.safety_line_ids.filtered('worn').mapped('name')

    def _vc_safety_text(self):
        """The line in the customer's "inspecting your device" WhatsApp ('' without the checks)."""
        worn = self._vc_worn()
        return '\n' + _("Safety check done ✅ %s", ', '.join(worn)) if worn else ''

    def _fs_track_block(self):
        """My orders: the safety check, with the technician's photo wearing it (as on Urban Company)."""
        out = super()._fs_track_block()
        worn = self._vc_worn()
        if worn and self.state in ('in_progress', 'done'):
            photo = self.sudo().safety_photo_ids.filtered('image')[:1]
            uri = None
            if photo:
                raw = base64.b64decode(photo.image)
                small = image_process(raw, size=(320, 320))
                uri = 'data:%s;base64,%s' % (guess_mimetype(small, default='image/jpeg'),
                                             base64.b64encode(small).decode())
            out['safety'] = {'items': worn, 'at': _iso(self.checks_done_on), 'photo': uri}
        return out

    # ------------------------------------------------------------------ the phone page
    def _vc_view(self):
        """The checks as the technician's page draws them."""
        self.ensure_one()
        visit = self.sudo()
        return {
            'warranty': visit._vc_warranty_view(),
            'safety': [{'id': line.id, 'name': line.name, 'required': line.required, 'done': line.worn}
                       for line in visit.safety_line_ids.sorted(lambda l: (l.sequence, l.id))
                       if line.item_id.active],
            'safety_photos': len(visit.safety_photo_ids.filtered('image')),
            'safety_photos_min': MIN_SAFETY_PHOTOS,
            'safety_photos_max': MAX_SAFETY_PHOTOS,
            'sides': [{'id': photo.id, 'name': photo.angle_id.name, 'required': photo.angle_id.required,
                       'done': bool(photo.image)}
                      for photo in visit.device_photo_ids.sorted(lambda p: (p.sequence, p.id))
                      if photo.angle_id.active],
            'video': bool(visit.device_video),
            'missing': visit._vc_missing(),
        }

    def _fs_tech_view(self):
        view = super()._fs_tech_view()
        if self.state == 'arrived':
            self._vc_prepare()
            view['checks'] = self._vc_view()
        return view

    def _vc_tech_act(self, action, item_id=None, done=None, photo_id=None, data=None, name=None, answer=None):
        """One change from the phone page. Returns None, or an error in words."""
        self.ensure_one()
        visit = self.sudo()
        if visit.state != 'arrived':
            return _("The checks are done after arriving and before starting work.")
        if action == 'check_warranty':
            if answer not in dict(WARRANTY_ANSWERS):
                return _("Choose the answer about the brand's warranty.")
            self._vc_warranty(answer)
            return None
        if action == 'check_tick':
            line = visit.safety_line_ids.filtered(lambda l: l.id == item_id)
            if not line:
                return _("Unknown item.")
            line.write({'worn': bool(done)})
            return None
        if action == 'check_clear_safety':
            visit.safety_photo_ids.unlink()
            return None
        try:
            raw = base64.b64decode(data or '', validate=True)
        except (ValueError, TypeError):
            return _("The file could not be read.")
        kind = _sniff(raw)
        if action in ('check_safety_photo', 'check_side_photo'):
            if kind != 'image':
                return _("That is not a photo.")
            if len(raw) > PHOTO_BYTES:
                return _("The photo is too large.")
            if action == 'check_safety_photo':
                if len(visit.safety_photo_ids) >= MAX_SAFETY_PHOTOS:
                    return _("At most %s safety photos. Clear them to take new ones.", MAX_SAFETY_PHOTOS)
                self.env['fix.visit.check.photo'].sudo().create(
                    {'visit_id': visit.id, 'kind': 'safety', 'image': base64.b64encode(raw)})
                return None
            photo = visit.device_photo_ids.filtered(lambda p: p.id == photo_id)
            if not photo:
                return _("Unknown side.")
            photo.image = base64.b64encode(raw)     # a retake replaces the photo
            return None
        if action == 'check_video':
            if kind != 'video':
                return _("That is not a video.")
            if len(raw) > VIDEO_BYTES:
                return _("The video is too large (at most 30 MB - keep it under a minute).")
            visit.write({'device_video': base64.b64encode(raw), 'device_video_name': (name or 'device-video')[:80]})
            return None
        return _("Unknown action.")

    def _fs_tech_do(self, action='', **kw):
        """Adds the checks to the technician's steps (page or My Visits): the changes above,
        and no Start while something is missing."""
        visit = self.sudo()
        if action.startswith('check_'):
            try:
                with self.env.cr.savepoint():
                    problem = visit._vc_tech_act(action, item_id=kw.get('item_id'), done=kw.get('done'),
                                                 photo_id=kw.get('photo_id'), data=kw.get('data'),
                                                 name=kw.get('name'), answer=kw.get('answer'))
            except (UserError, ValidationError) as err:
                problem = err.args[0] if action == 'check_warranty' else _("This photo could not be read. Take it again.")
            view = visit._fs_tech_view()
            return dict(view, ok=False, error='check', message=problem) if problem else view
        if action == 'start' and visit.state == 'arrived':
            missing = visit._vc_missing()
            if missing:
                return dict(visit._fs_tech_view(), ok=False, error='checks',
                            message=_("Finish the checks first: %s", ', '.join(missing)))
            visit._vc_stamp()
            return super(ServiceVisit, visit.with_context(fix_checks_passed=True))._fs_tech_do(action, **kw)
        return super()._fs_tech_do(action, **kw)


class JobCard(models.Model):
    _inherit = 'job.card'

    def action_start_inspection(self):
        """Start Diagnosis is the same moment as the technician's Start work, at the customer's
        door. On a home-visit card it waits for the technician to arrive and do the safety check
        (gloves, mask, ...) - the "Before you start" window opens when that is still to do - and
        then starts the visit too. Cards with no open visit (e.g. the device is at the office)
        start as before."""
        if self.env.context.get('fix_checks_passed'):
            return super().action_start_inspection()
        states = dict(self.env['fix.service.visit']._fields['state'].selection)
        plain = self.browse()
        for card in self:
            visit = card.sudo().fs_visit_ids.filtered(
                lambda v: v.state not in ('done', 'cancelled')).sorted('id', reverse=True)[:1]
            if not visit or visit.state == 'in_progress':
                plain |= card
                continue
            if visit.state != 'arrived':
                raise UserError(_(
                    "%(card)s: the technician is not at the customer yet (visit %(visit)s is %(state)s). "
                    "The diagnosis starts at the door: the technician marks Arrived, does the safety check "
                    "(gloves, mask, ...) and the photos, then taps Start work.",
                    card=card.name, visit=visit.name, state=states.get(visit.state, visit.state)))
            if visit._vc_missing():
                if len(self) > 1:
                    raise UserError(_("Do the checks of %s before starting the diagnosis.", visit.name))
                return visit.with_env(self.env).action_open_checks()
            # checks done: Start work, which also starts this diagnosis (service_visit.action_start)
            visit._vc_stamp()
            visit.with_env(self.env).with_context(fix_checks_passed=True).action_start()
        return super(JobCard, plain).action_start_inspection() if plain else True


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    def _notify_customer(self, key):
        """"Inspecting your device" also says the safety check was done ({safety})."""
        if key != 'inspection':
            return super()._notify_customer(key)
        for order in self:
            visit = order.sudo()._fs_current_visit()
            extra = dict(self.env.context.get('osm_extra') or {},
                         safety=visit._vc_safety_text() if visit else '')
            super(OnlineServiceOrder, order.with_context(osm_extra=extra))._notify_customer(key)
        return None
