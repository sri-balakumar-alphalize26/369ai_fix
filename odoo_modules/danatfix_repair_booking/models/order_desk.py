# -*- coding: utf-8 -*-
"""The Live Screen, its two alarms and the staff WhatsApp poll, on the website
orders (online.service.order) that 369ai_fix (booking/) turns into job cards.

Approve and Reject are 369ai_fix's (estimate, slot link, reason); this
module adds where staff do it - the screen, any Odoo page, the WhatsApp group - and
"calling the customer". Every change goes through `_desk_lock`, so a tap in the
group and a click on the screen in the same second cannot both win.
"""
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .booking import OPT_ACCEPT, OPT_CALL, OPT_REJECT, POLL_OPTIONS  # noqa: F401  (same poll words)

_logger = logging.getLogger(__name__)


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


class OnlineServiceOrder(models.Model):
    _inherit = 'online.service.order'

    desk_calling = fields.Boolean('Calling the customer', readonly=True, copy=False, tracking=True)
    desk_calling_by = fields.Char('Calling: who', readonly=True, copy=False)
    desk_reject_pending = fields.Boolean('Reject: reason needed', readonly=True, copy=False,
                                         help="Someone tapped Reject in the WhatsApp group; the reason is "
                                              "written on the Live Screen before the customer is told.")
    desk_needs_screen = fields.Text('Needs the screen', readonly=True, copy=False,
                                    help="Accepted on WhatsApp but cannot be approved from there.")
    poll_sent = fields.Boolean(readonly=True, copy=False)
    poll_wa_id = fields.Char('Poll message id', readonly=True, copy=False, index=True)
    poll_error = fields.Char(readonly=True, copy=False)

    # ------------------------------------------------------------------
    # New booking: screens and the staff group
    # ------------------------------------------------------------------
    @api.model
    def website_create(self, payload):
        result = super().website_create(payload)
        if isinstance(result, dict) and result.get('ok') and not result.get('duplicate'):
            site = self.env['online.service.site']._for_host((payload or {}).get('host'))
            order = self.sudo().search([('name', '=', result.get('ref')), ('site_id', '=', site.id)], limit=1)
            if order:
                order._desk_notify()
                try:
                    with self.env.cr.savepoint():
                        order._desk_post_to_group()
                except Exception:  # noqa: BLE001 - the booking and the alarm never depend on WhatsApp
                    _logger.exception("Website booking %s: staff group post failed", order.name)
        return result

    def _desk_notify(self):
        try:
            self.env['bus.bus']._sendone('danatfix_booking', 'danatfix_booking/refresh', {'ids': self.ids})
        except Exception as err:  # noqa: BLE001 - the 20 s poll catches up
            _logger.warning("Website booking: bus notify failed: %s", err)

    def _ring(self):
        res = super()._ring()
        self._desk_notify()
        return res

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------
    @api.model
    def desk_alarm_state(self):
        """Both alarms, small enough to poll from every Odoo page."""
        settings = self.env['danatfix.booking.settings'].get_settings()
        hears = not settings.alarm_user_ids or self.env.user in settings.alarm_user_ids
        Order = self.sudo()
        new = Order.search([('state', '=', 'new'), ('desk_calling', '=', False),
                            ('company_id', 'in', self.env.companies.ids)])
        slots = Order.search([('slot_booked_on', '!=', False), ('slot_seen_by_id', '=', False),
                              ('state', '!=', 'cancelled'), ('company_id', 'in', self.env.companies.ids)])
        return {
            'new': len(new) if hears else 0,
            'slots': [{'id': o.id, 'name': o.name, 'customer': o.customer_name or o.phone or '',
                       'slot': o.slot_label or ''} for o in slots[:10]] if hears else [],
            'ring': max(3, settings.ring_seconds or 20),
            'repeat': max(3, settings.repeat_seconds or 15),
        }

    @api.model
    def alarm_state(self):
        """Online Service's own alarm stays quiet while the Live Screen's rings."""
        state = super().alarm_state()
        if self.env['danatfix.booking.settings'].get_settings().desk_replaces_online_alarm:
            state.update({'count': 0, 'orders': []})
        return state

    # ------------------------------------------------------------------
    # Live Screen
    # ------------------------------------------------------------------
    @api.model
    def desk_screen_data(self):
        """New bookings (oldest first) and booked visit times not yet seen."""
        settings = self.env['danatfix.booking.settings'].get_settings()
        domain = [('company_id', 'in', self.env.companies.ids), '|',
                  ('state', '=', 'new'),
                  '&', ('slot_booked_on', '!=', False), ('slot_seen_by_id', '=', False)]
        orders = self.search(domain + [('state', '!=', 'cancelled')], order='id asc', limit=200)
        return {
            'rows': [o._desk_row() for o in orders],
            'new': len(orders.filtered(lambda o: o.state == 'new')),
            'slots': len(orders.filtered(lambda o: o.slot_booked_on and not o.slot_seen_by_id)),
            'ring': max(3, settings.ring_seconds or 20),
            'repeat': max(3, settings.repeat_seconds or 15),
            'poll_ready': bool(settings.poll_enabled and settings._group_jid()),
        }

    def _desk_row(self):
        self.ensure_one()
        order = self.sudo()
        cards = order.job_card_ids.filtered(lambda c: c.state != 'cancelled')
        photos = order.env['ir.attachment'].search(
            [('res_model', '=', 'job.card'), ('res_id', 'in', cards.ids), ('mimetype', 'like', 'image/')], limit=6)
        videos = order.env['ir.attachment'].search_count(
            [('res_model', '=', 'job.card'), ('res_id', 'in', cards.ids), ('mimetype', 'like', 'video/')])
        _estimate, total = order._wb_estimate()
        return {
            'id': order.id,
            'name': order.name,
            'state': order.state,
            'stage': ('reject' if order.desk_reject_pending else 'calling' if order.desk_calling
                      else 'slot' if order.state != 'new' else 'new'),
            'mode': dict(order._fields['mode'].selection).get(order.mode, ''),
            'customer': order.customer_name or '',
            'numbers': [{'label': label, 'number': number, 'digits': _digits(number)}
                        for label, number in order._wb_numbers()],
            'area': order.area or '',
            'address': order.address or '',
            'map_url': order.map_url or '',
            'problem': order.problem or '',
            'lines': [{'id': l.id, 'device': l.device or '', 'model': l.model or '', 'issue': l.issue or '',
                       'qty': l.qty or 1, 'price': l.product_id.lst_price if l.product_id else None}
                      for l in order.line_ids],
            'parts': [{'name': l.description or l.product_id.display_name, 'qty': l.quantity,
                       'on_hand': l.product_id.qty_available} for l in cards.spare_part_line_ids],
            'job_cards': [{'id': c.id, 'name': c.name} for c in cards],
            'total': total,
            'currency': (order.company_id or self.env.company).currency_id.name,
            'photos': photos.ids,
            'videos': videos,
            'slot': order.slot_label or '',
            'slot_unseen': bool(order.slot_booked_on and not order.slot_seen_by_id),
            'calling_by': order.desk_calling_by or '',
            'needs_screen': order.desk_needs_screen or '',
            'note': order.note or '',
            'created': fields.Datetime.to_string(order.create_date),
            'poll_sent': order.poll_sent,
            'poll_error': order.poll_error or '',
        }

    def desk_act(self, action):
        """A button on the Live Screen. Approve and Reject open their dialogs."""
        self.ensure_one()
        if action == 'approve':
            self.action_mark_opened()
            return {'action': self.action_wb_approve()}
        if action == 'reject':
            self.action_mark_opened()
            return {'action': self.action_wb_reject()}
        if action == 'call':
            ok, warning = self._desk_set_calling(self.env.user.name)
        elif action == 'seen':
            self.action_wb_slot_seen()
            ok, warning = True, ''
        else:
            raise UserError(_("Unknown action."))
        data = self.desk_screen_data()
        if not ok:
            data['warning'] = warning
        return data

    def _desk_lock(self):
        """Lock the order row; (state, calling) as they really are now."""
        self.ensure_one()
        self.flush_recordset(['state', 'desk_calling'])
        self.env.cr.execute('SELECT state, desk_calling FROM online_service_order WHERE id = %s FOR UPDATE',
                            [self.id])
        row = self.env.cr.fetchone() or (self.state, self.desk_calling)
        self.invalidate_recordset(['state', 'desk_calling', 'desk_calling_by'])
        return row

    def _desk_set_calling(self, who, via='screen'):
        state, calling = self._desk_lock()
        if state != 'new':
            return False, _("%s was already handled.", self.name)
        if calling:
            return False, _("%(who)s is already calling for %(ref)s.", who=self.desk_calling_by, ref=self.name)
        self.sudo().write({'desk_calling': True, 'desk_calling_by': who})
        self.action_mark_opened()
        self.message_post(body=_("%(who)s is calling the customer (%(via)s).", who=who,
                                 via=_("WhatsApp poll") if via == 'whatsapp' else _("Live Screen")))
        self._desk_tell_group('call', who, via)
        self._desk_notify()
        return True, ''

    # ------------------------------------------------------------------
    # Approve / reject: tell the group too
    # ------------------------------------------------------------------
    def _wb_do_approve(self, technician=None, days=0):
        self._desk_lock()
        res = super()._wb_do_approve(technician=technician, days=days)
        self.sudo().write({'desk_calling': False, 'desk_needs_screen': False})
        self._desk_tell_group('approve', self.env.user.name, 'screen')
        self._desk_notify()
        return res

    def _wb_do_reject(self, reason, by_customer=False):
        self._desk_lock()
        res = super()._wb_do_reject(reason, by_customer=by_customer)
        self.sudo().write({'desk_calling': False, 'desk_reject_pending': False, 'desk_needs_screen': False})
        self._desk_tell_group('reject', _("the customer") if by_customer else self.env.user.name, 'screen',
                              reason=reason)
        self._desk_notify()
        return res

    @api.model
    def slot_book(self, host, ref, token, slot_id, date):
        res = super().slot_book(host, ref, token, slot_id, date)
        if isinstance(res, dict) and res.get('ok'):
            site = self.env['online.service.site']._for_host(host)
            order = self.sudo().search([('name', '=', ref), ('site_id', '=', site.id)], limit=1)
            order._desk_tell_group('slot', order.customer_name or '', 'website')
            order._desk_notify()
        return res

    # ------------------------------------------------------------------
    # The staff WhatsApp group
    # ------------------------------------------------------------------
    def _desk_target(self):
        settings = self.env['danatfix.booking.settings'].get_settings()
        if not settings.poll_enabled:
            return None, None
        jid = settings._group_jid()
        session = settings._session() if jid else None
        return (session, jid) if session and jid else (None, None)

    def _desk_send(self, session, jid, text):
        try:
            with self.env.cr.savepoint():
                session.send_message(jid, text)
        except Exception as err:  # noqa: BLE001
            if type(err).__name__ == 'WhatsAppQueued':
                return ''
            return str(err)[:200] or type(err).__name__
        return ''

    def _desk_staff_text(self):
        self.ensure_one()
        order = self.sudo()
        out = [_("📥 *New website booking %s*", order.name)]
        site = ' · '.join(p for p in (order.site_id.name, dict(order._fields['mode'].selection).get(order.mode)) if p)
        if site:
            out.append(site)
        if order.customer_name:
            out.append('👤 %s' % order.customer_name)
        for label, number in order._wb_numbers():
            out.append('📞 %s: %s' % (label, number))
        where = ', '.join(p for p in (order.address, order.area) if p)
        if where:
            out.append('📍 %s' % where)
        if order.map_url:
            out.append(order.map_url)
        for line in order.line_ids:
            what = ' '.join(p for p in (line.device, line.model) if p)
            out.append('🔧 %s%s' % ('%s — ' % what if what else '', line.issue))
        if order.problem:
            out.append('📝 %s' % order.problem)
        if order.job_card_ids:
            out.append(_("🗂 Job card: %s", ', '.join(order.job_card_ids.mapped('name'))))
        return '\n'.join(out)

    def _desk_post_to_group(self):
        """The booking, then the poll. Never raises."""
        self.ensure_one()
        session, jid = self._desk_target()
        if not session:
            return
        error = self._desk_send(session, jid, self._desk_staff_text())
        if not error:
            try:
                with self.env.cr.savepoint():
                    session.sa_send_poll(jid, _("%s — who takes this job?", self.name), POLL_OPTIONS)
            except Exception as err:  # noqa: BLE001
                if type(err).__name__ != 'WhatsAppQueued':
                    error = str(err)[:200] or type(err).__name__
        if error:
            self.sudo().write({'poll_error': error})
            self.message_post(body=_("WhatsApp poll not sent: %s", error))
            return
        vals = {'poll_sent': True, 'poll_error': False}
        sent = self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', session.id), ('direction', '=', 'outgoing'),
            ('phone', 'in', [jid, jid.split('@')[0]]), ('message', 'ilike', self.name),
            ('wa_message_id', '!=', False),
            ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), seconds=60)),
        ], order='id desc', limit=1)
        if sent:
            vals['poll_wa_id'] = sent.wa_message_id
        self.sudo().write(vals)

    def _desk_tell_group(self, action, who, via, reason=''):
        """One short line in the group, only when the group had the booking."""
        self.ensure_one()
        if not self.poll_sent:
            return
        session, jid = self._desk_target()
        if not session:
            return
        where = _(" on the Live Screen") if via == 'screen' else ''
        text = {
            'approve': _("✅ %(ref)s approved by %(who)s%(where)s. The customer was sent the estimate."),
            'call': _("📞 %(who)s is calling the customer for %(ref)s%(where)s."),
            'reject': _("❌ %(ref)s rejected by %(who)s: %(reason)s"),
            'reject_pending': _("❌ %(who)s wants to reject %(ref)s - write the reason on the Live Screen."),
            'needs_screen': _("⚠️ %(ref)s: %(reason)s - finish it on the Live Screen."),
            'slot': _("🗓 %(ref)s: %(who)s booked the visit for %(slot)s."),
        }[action] % {'ref': self.name, 'who': who, 'where': where, 'reason': reason, 'slot': self.slot_label or ''}
        error = self._desk_send(session, jid, text)
        if error:
            _logger.info("Website booking %s: group note not sent: %s", self.name, error)

    @api.model
    def _desk_from_poll_ref(self, poll_ref):
        """The order a WhatsApp vote belongs to, or empty."""
        poll_ref = (poll_ref or '').strip()
        if not poll_ref:
            return self.browse()
        Order = self.sudo()
        order = Order.search([('poll_wa_id', '=', poll_ref)], limit=1)
        if order:
            return order
        row = self.env['whatsapp.message'].sudo().search(
            [('wa_message_id', '=', poll_ref), ('direction', '=', 'outgoing')], limit=1)
        match = re.search(r'\bOS/\d+', row.message or '')
        order = Order.search([('name', '=', match.group(0))], limit=1) if match else Order.browse()
        if order and not order.poll_wa_id:
            order.poll_wa_id = poll_ref
        return order

    def _desk_apply_vote(self, choice, digits, push_name):
        """A tap in the staff group. The first tap decides; late or changed votes are ignored."""
        self.ensure_one()
        label = (choice or '').lower()
        action = ('accept' if 'accept' in label else 'call' if 'call' in label
                  else 'reject' if 'reject' in label else '')
        state, calling = self._desk_lock()
        if not action or state != 'new' or self.desk_reject_pending:
            return False
        who = push_name or digits or _('someone')
        user = self.env['danatfix.booking']._user_for_digits(digits)
        if action == 'call':
            if calling:
                return False
            return self._desk_set_calling(who, via='whatsapp')[0]
        if action == 'reject':
            self.sudo().write({'desk_reject_pending': True})
            self.message_post(body=_("%s tapped Reject on WhatsApp: the reason must be written on the Live Screen.", who))
            self._desk_tell_group('reject_pending', who, 'whatsapp')
            self._desk_notify()
            return True
        # Accept: approve only when nothing is left to decide on the screen.
        cards = self.job_card_ids.filtered(lambda c: c.state != 'cancelled')
        problem = ''
        if not cards.service_line_ids:
            problem = _("no priced repair on the job card")
        elif self._wb_missing_parts():
            problem = _("parts must be ordered (how many days?)")
        if problem:
            self.sudo().write({'desk_needs_screen': problem})
            self._desk_tell_group('needs_screen', who, 'whatsapp', reason=problem)
            self._desk_notify()
            return True
        approver = self.with_user(user).sudo() if user else self.sudo()
        approver._wb_do_approve()
        self.message_post(body=_("Approved from the WhatsApp poll by %s.", who))
        return True
