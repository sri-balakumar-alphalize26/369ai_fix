# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def _clean_host(host):
    """'WWW.DanatFix.com:443' -> 'www.danatfix.com'."""
    host = (host or '').strip().lower()
    if '://' in host:
        host = host.split('://', 1)[1]
    return host.split('/', 1)[0].split(':', 1)[0]


class OnlineServiceSite(models.Model):
    """A website allowed to send orders to THIS database.

    The website picks the database by its own host name; this record is the
    other half of the handshake: an order from a host that is not listed here
    (or switched off) is refused. Another site -> another database is just
    another record in that database, no code change.
    """
    _name = 'online.service.site'
    _description = 'Online Service Website'
    _order = 'sequence, id'

    name = fields.Char(required=True, help="Shown to staff and used in WhatsApp messages, e.g. Danat Fix.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    domains = fields.Char(
        required=True,
        help="Host names of the website, comma separated, e.g. danatfix.com, www.danatfix.com")
    public_url = fields.Char(
        'Website URL',
        help="Used for the tracking link in WhatsApp messages, e.g. https://danatfix.com")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    alarm = fields.Boolean('Alarm on new orders', default=True)
    whatsapp_messages = fields.Boolean('WhatsApp the customer at every status', default=True)
    whatsapp_session = fields.Selection(
        selection='_whatsapp_session_selection', string='WhatsApp number',
        help="Which WhatsApp session sends the status messages and login codes. "
             "Empty = the first connected one.")
    order_count = fields.Integer(compute='_compute_order_count')

    @api.model
    def _whatsapp_session_selection(self):
        if 'whatsapp.session' not in self.env:
            return []
        sessions = self.env['whatsapp.session'].sudo().search([])
        return [(str(s.id), s.name) for s in sessions]

    def _compute_order_count(self):
        data = self.env['online.service.order']._read_group(
            [('site_id', 'in', self.ids)], ['site_id'], ['__count'])
        counts = {site.id: n for site, n in data}
        for site in self:
            site.order_count = counts.get(site.id, 0)

    @api.constrains('domains', 'active')
    def _check_domains(self):
        for site in self:
            hosts = site._hosts()
            if not hosts:
                raise ValidationError(_("Give at least one host name."))
            for other in self.with_context(active_test=False).search([('id', '!=', site.id)]):
                both = set(hosts) & set(other._hosts())
                if both:
                    raise ValidationError(_(
                        "%(host)s is already used by the website %(site)s.",
                        host=', '.join(sorted(both)), site=other.name))

    def _hosts(self):
        self.ensure_one()
        return [h for h in (_clean_host(x) for x in (self.domains or '').split(',')) if h]

    @api.model
    def _for_host(self, host):
        """The ACTIVE website for this host name, or an empty recordset."""
        host = _clean_host(host)
        if not host:
            return self.browse()
        for site in self.sudo().search([]):
            if host in site._hosts():
                return site
        return self.browse()

    def _track_url(self):
        self.ensure_one()
        base = (self.public_url or '').strip().rstrip('/')
        if not base:
            hosts = self._hosts()
            base = 'https://%s' % hosts[0] if hosts else ''
        return base + '/track' if base else ''

    def _wa_session(self):
        """The WhatsApp session to send with, or None (gateway missing / nothing usable)."""
        self.ensure_one()
        if 'whatsapp.session' not in self.env:
            return None
        Session = self.env['whatsapp.session'].sudo()
        if self.whatsapp_session:
            session = Session.browse(int(self.whatsapp_session)).exists()
            if session:
                return session
        session = None
        if hasattr(Session, 'get_connected_session'):
            try:
                session = Session.get_connected_session()
            except Exception:  # noqa: BLE001 - gateway down: fall back below
                session = None
        return session or Session.search([('use_whatsapp', '=', True)], limit=1) or None

    def _wa_send(self, phone, text):
        """Send one WhatsApp text. Returns (status, detail); never raises."""
        self.ensure_one()
        session = self._wa_session()
        if not session:
            return 'skipped', _("No WhatsApp session")
        try:
            ok = session.send_message(phone, text)
        except Exception as err:  # noqa: BLE001
            # The gateway raises WhatsAppQueued when it accepted the message
            # for a later retry: that is a success for us.
            if type(err).__name__ == 'WhatsAppQueued':
                return 'queued', str(err)[:200]
            _logger.warning("Online Service WhatsApp to %s failed: %s", phone, err)
            return 'error', (str(err) or type(err).__name__)[:200]
        if ok:
            return 'sent', ''
        return 'blocked', _("Not sent: WhatsApp switched off or blocked by the gateway policy")

    def _wa_deliver(self, phone, text, order=None, who='customer'):
        """_wa_send, and the message kept as sent: the Booking Desk's WhatsApp tab shows what
        the customer or the technician got, even while WhatsApp is not connected."""
        self.ensure_one()
        status, detail = self._wa_send(phone, text)
        self.env['online.service.wa.message']._keep(self, phone, text, status, detail, order=order, who=who)
        return status, detail

    def action_view_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            '369ai_fix.action_online_order_all')
        action['domain'] = [('site_id', '=', self.id)]
        action['context'] = {}
        return action
