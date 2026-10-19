# -*- coding: utf-8 -*-
"""The green screens in a real browser: every menu's screen draws without a JavaScript
error, a record opens on the right, and the Booking Desk's tabs show the booking with
the green record screen (no Odoo dialog). Needs Chrome (Odoo skips browser tests
without it)."""
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

from ..app.models.fix_screen_configs import SCREENS

HOST = 'screen-ui.example'

WAIT = """
const wait = (sel, ms = 20000) => new Promise((resolve, reject) => {
    const t0 = Date.now();
    const tick = () => {
        const el = document.querySelector(sel);
        if (el) { return resolve(el); }
        if (document.querySelector('.o_error_dialog')) {
            return reject(new Error('Odoo error dialog: ' + document.querySelector('.o_error_dialog').innerText.slice(0, 400)));
        }
        if (Date.now() - t0 > ms) {
            const note = document.querySelector('.o_notification');
            const layer = document.querySelector('.fxp-layer');
            return reject(new Error('missing ' + sel + (note ? ' (notice: ' + note.innerText + ')' : '')
                + (layer ? ' (pop-up: ' + layer.innerText.slice(0, 300) + ')' : ' (no pop-up)')));
        }
        setTimeout(tick, 100);
    };
    tick();
});
const noDialog = () => {
    if (document.querySelector('.o_dialog, .modal.show')) { throw new Error('an Odoo dialog opened'); }
};
"""

SCREEN_JS = WAIT + """
(async () => {
    await wait('.o_fxs .fxs');
    await wait('.o_fxs .fxs-table, .o_fxs .fxs-record h2, .o_fxs .fxd-empty');
    const err = document.querySelector('.o_fxs .fxs-err');
    if (err) { throw new Error('screen error: ' + err.innerText); }
    const row = document.querySelector('.o_fxs .fxs-body .fxs-row');
    if (row) {
        row.click();
        await wait('.o_fxs .fxs-pane .fxs-record .fxs-rtitle h2');
    }
    noDialog();
    console.log('test successful');
})().catch((e) => console.error(e.message));
"""

DESK_JS = WAIT + """
(async () => {
    await wait('.o_fxd .fxd-body');
    const card = await wait('.o_fxd .fxd-card');
    card.click();
    await wait('.o_fxd .fxd-detail .fxd-tabs');
    // the Booking tab draws the booking with the green record screen
    [...document.querySelectorAll('.o_fxd .fxd-tab')].find((b) => b.innerText.includes('Booking')).click();
    await wait('.o_fxd .fxd-detail .fxs-record .fxs-rtitle h2');
    noDialog();
    console.log('test successful');
})().catch((e) => console.error(e.message));
"""


@tagged('post_install', '-at_install')
class TestScreensInTheBrowser(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login='screen_ui', password='screen_ui_pass_1',
            groups='base.group_user,base.group_system,mobile_repair.group_mobile_repair_manager,'
                   '369ai_fix.group_fix_website_editor,stock.group_stock_user')
        cls.site = cls.env['online.service.site'].create({'name': 'Screen UI', 'domains': HOST})
        with patch.object(type(cls.env['online.service.site']), '_wa_send', lambda *a, **k: ('sent', '')):
            result = cls.env['online.service.order'].website_create({
                'host': HOST, 'mode': 'doorstep', 'name': 'Browser Test', 'phone': '+968 9000 1212',
                'area': 'Qurum', 'lines': [{'device': 'Mobile Phones', 'model': 'X', 'issue': 'Screen', 'qty': 1}],
            })
        cls.order = cls.env['online.service.order'].search([('name', '=', result['ref'])])

    def _path(self, key):
        action = self.env.ref('369ai_fix.action_screen_%s' % key)
        return '/odoo/%s' % action.path

    def test_every_screen_draws(self):
        for key, cfg in SCREENS.items():
            if cfg['model'] not in self.env:
                continue
            with self.subTest(screen=key):
                self.browser_js(self._path(key), SCREEN_JS, login='screen_ui', timeout=90)

    def test_the_desk_tabs(self):
        self.browser_js('/odoo/fix-desk', DESK_JS, login='screen_ui', timeout=90)
