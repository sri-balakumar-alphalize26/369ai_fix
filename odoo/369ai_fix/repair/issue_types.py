"""Which mobile_repair issue types each of the website's repairs fixes.

Keyed by the repair's internal reference (as created by the install hook), valued by
mobile_repair issue-type xml ids without the module prefix. Filled only where a repair
has no issue types yet, so choices made in Odoo are never overwritten.
"""
import logging

_logger = logging.getLogger(__name__)

ISSUE_TYPES = {
    'MOB-SCREEN-REPLACEMENT': ['screen_cracked', 'display_not_working', 'touch_not_working'],
    'MOB-BATTERY-REPLACEMENT': ['battery_drain'],
    'MOB-CHARGING-PORT': ['charging_port_damaged', 'battery_not_charging'],
    'MOB-BACK-GLASS': ['back_glass_broken'],
    'MOB-CAMERA': ['camera_not_working'],
    'MOB-SPEAKER-MICROPHONE': ['speaker_not_working', 'microphone_not_working', 'earpiece_not_working'],
    'MOB-WATER-DAMAGE': ['water_damage'],
    'MOB-SOFTWARE-AND-DATA': ['software_issue', 'boot_loop', 'password_frp'],
    'TAB-SCREEN-GLASS': ['screen_cracked'],
    'TAB-DISPLAY-TOUCH-NOT-WORKING': ['display_not_working', 'touch_not_working', 'backlight_not_working'],
    'TAB-BATTERY-REPLACEMENT': ['battery_drain'],
    'TAB-CHARGING-PORT': ['charging_port_damaged', 'battery_not_charging'],
    'TAB-BUTTONS': ['buttons_not_working'],
    'TAB-SOFTWARE-AND-DATA': ['software_issue', 'boot_loop'],
    'LAP-SCREEN-REPLACEMENT': ['screen_cracked', 'display_not_working', 'backlight_not_working'],
    'LAP-KEYBOARD-TRACKPAD': ['keyboard_issue', 'trackpad_mouse'],
    'LAP-BATTERY-REPLACEMENT': ['battery_drain', 'battery_not_charging'],
    'LAP-HINGE-REPAIR': ['hinge_damaged'],
    'LAP-NOT-POWERING-ON': ['device_dead'],
    'LAP-MOTHERBOARD-REPAIR': ['motherboard_issue'],
    'LAP-SSD-RAM-UPGRADE': ['hdd_ssd_issue', 'ram_issue'],
    'LAP-OS-INSTALL-AND-VIRUS-REMOVAL': ['os_reinstall', 'virus_malware', 'slow_performance'],
    'LAP-OVERHEATING-FAN': ['overheating', 'fan_cooling'],
    'DSK-NOT-POWERING-ON': ['device_dead'],
    'DSK-POWER-SUPPLY': ['device_dead', 'random_restart'],
    'DSK-MOTHERBOARD-REPAIR': ['motherboard_issue'],
    'DSK-SSD-RAM-UPGRADE': ['hdd_ssd_issue', 'ram_issue'],
    'DSK-GRAPHICS-CARD': ['hdmi_display_port', 'display_not_working'],
    'DSK-OS-INSTALL-AND-VIRUS-REMOVAL': ['os_reinstall', 'virus_malware', 'slow_performance'],
    'PRN-NOT-CONNECTING-WI-FI-USB': ['wifi_bluetooth', 'usb_port'],
    'PRN-SETUP-AND-INSTALLATION': ['driver_issue'],
    'DATA-DELETED-FILES': ['data_recovery'],
    'DATA-DRIVE-NOT-DETECTED': ['data_recovery', 'hdd_ssd_issue'],
    'DATA-CLICKING-DEAD-HARD-DISK': ['data_recovery', 'hdd_ssd_issue'],
    'DATA-FORMATTED-DRIVE': ['data_recovery'],
    'DATA-WATER-FIRE-DAMAGE': ['data_recovery', 'water_damage'],
    'DATA-PHONE-DATA-RECOVERY': ['data_recovery'],
    'ITS-SOFTWARE-INSTALLATION': ['software_issue', 'driver_issue'],
    'ITS-SLOW-COMPUTER-TUNE-UP': ['slow_performance'],
    'ITS-VIRUS-AND-MALWARE-REMOVAL': ['virus_malware'],
    'ITS-PRINTER-AND-NETWORK-SETUP': ['driver_issue'],
}


def fill_issue_types(env):
    Template = env['product.template'].with_context(active_test=False)
    filled = 0
    for code, xml_ids in ISSUE_TYPES.items():
        product = Template.search([('default_code', '=', code)], limit=1)
        if not product or product.repair_issue_type_ids:
            continue
        types = env['job.card.issue.type']
        for xml_id in xml_ids:
            types |= env.ref('mobile_repair.issue_type_%s' % xml_id, raise_if_not_found=False) or types.browse()
        if types:
            product.repair_issue_type_ids = [(6, 0, types.ids)]
            filled += 1
    _logger.info('369ai_fix: issue types set on %d repair services', filled)
    return filled


# Our own categories the AI list does not know about.
EXTRA_CATEGORIES = {
    'data_recovery': ['Data Recovery'],
    'hdd_ssd_issue': ['Data Recovery'],
    'virus_malware': ['IT Support'],
    'software_issue': ['IT Support'],
    'driver_issue': ['IT Support', 'Printer'],
    'slow_performance': ['IT Support'],
    'os_reinstall': ['IT Support'],
    'wifi_bluetooth': ['Networking & Wi-Fi'],
}


def import_ai_issue_types(env):
    """Issue types from the Alphalize Repair AI package (data/issue_types_ai.json):
    links mobile_repair's own types to their device categories and adds the ones it
    lacks. Matched by xml id or name, so it never duplicates; categories already set
    in Odoo are kept and only added to."""
    import json
    from odoo.tools import file_open
    with file_open('369ai_fix/repair/data/issue_types_ai.json') as f:
        data = json.load(f)
    Category = env['device.category'].with_context(active_test=False)
    cats = {c.name: c for c in Category.search([])}
    Issue = env['job.card.issue.type'].with_context(active_test=False)

    def link(issue, names):
        wanted = Category.browse([cats[n].id for n in names if n in cats])
        missing = wanted - issue.device_category_ids
        if missing:
            issue.device_category_ids = [(4, c.id) for c in missing]

    linked = created = 0
    for row in data['existing']:
        issue = env.ref('mobile_repair.issue_type_%s' % row['existing'], raise_if_not_found=False)
        if issue:
            link(issue, row['categories'] + EXTRA_CATEGORIES.get(row['existing'], []))
            linked += 1
    sequence = max(Issue.search([]).mapped('sequence') or [0]) + 10
    for row in data['new']:
        issue = Issue.search([('name', '=ilike', row['name'])], limit=1)
        if not issue:
            issue = Issue.create({'name': row['name'], 'sequence': sequence})
            sequence += 10
            created += 1
        link(issue, row['categories'])
    _logger.info('369ai_fix: issue types linked to devices: %d, added: %d', linked, created)
    return linked, created
