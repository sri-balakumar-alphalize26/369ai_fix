"""Which problems each spare part fixes, guessed from its name.

At the visit the technician ticks what's wrong ("Screen cracked") and is offered the parts
that fix it (visits/: _vr_suggest). Parts with no problems yet get them here, and the device
types they fit when the name tells; staff correct them on the part afterwards. Parts that
already have problems are never changed.
"""
import logging
import re

_logger = logging.getLogger(__name__)

DISPLAY = ['Screen Cracked / Broken Display', 'Display Not Working / Black Screen', 'Touch Not Working',
           'Backlight Not Working', 'Lines on Display', 'Display Flickering', 'Display Discoloration / Dead Pixels',
           'Ghost Touch / Phantom Touches', 'Touch Working Partially', 'Watch Screen Cracked',
           'Watch Touch Not Responding']

# (name pattern, problems, device types when the name names none)
PART_RULES = [
    (r'\b(screen|display|lcd|oled|amoled|led|digitizer|touch\s*(screen|panel))\b', DISPLAY, []),
    (r'\bmonitor\b|\b\d{2}(\.\d)?\s*inch\b.*\b(ips|fhd|qhd|uhd)\b|\b\d{2,3}\s*hz\b',
     ['No Display Output', 'HDMI / Display Port Issue'], ['Desktop']),
    (r'\bbattery\b', ['Battery Drain / Battery Issue', 'Battery Not Charging', 'Battery Swollen',
                      'Device Not Turning On (Dead)', 'Watch Battery Draining Fast'], []),
    (r'charging\s*(port|flex|board|connector)|\bdock\s*connector|\b(type-c|usb-c|lightning)\s*port',
     ['Charging Port Damaged', 'Battery Not Charging', 'Slow Charging', 'Watch Not Charging'], []),
    (r'\bcharg(er|ing\s*adapter|ing\s*cable)\b', ['Battery Not Charging', 'Slow Charging', 'Watch Not Charging'], []),
    (r'wireless\s*charging|charging\s*coil', ['Wireless Charging Not Working'], ['Mobile Phone']),
    (r'back\s*(glass|panel|cover|housing)|\bhousing\b', ['Back Glass Broken', 'Back Panel / Housing Damaged'], []),
    (r'\b(frame|chassis)\b', ['Frame Bent / Damaged', 'Tablet Bent / Frame Damaged'], []),
    (r'\bcamera\b|\blens\b', ['Camera Not Working', 'Rear Camera Not Working', 'Front Camera Not Working',
                             'Camera Blurry / Out of Focus'], []),
    (r'\b(webcam|c920|brio)\b', ['Webcam Not Working'], ['Laptop']),
    (r'\b(speaker|loudspeaker|buzzer)\b', ['Speaker Not Working', 'No Sound / Audio'], []),
    (r'\bear\s*(piece|speaker)\b', ['Earpiece Not Working'], ['Mobile Phone']),
    (r'\b(mic|microphone)\b', ['Microphone Not Working'], []),
    (r'(headphone|audio)\s*jack|\b3\.5\s*mm\b', ['Audio Jack Issue'], []),
    (r'vibrat|taptic|haptic', ['Vibration Not Working'], ['Mobile Phone']),
    (r'\bsim\b', ['SIM Card Not Detected'], ['Mobile Phone', 'Tablet']),
    (r'\bantenna\b', ['Network / Signal Issue'], ['Mobile Phone', 'Tablet']),
    (r'\bwi-?fi\b|\bwlan\b|\bbluetooth\b', ['WiFi / Bluetooth Not Working'],
     ['Laptop', 'Desktop', 'Networking & Wi-Fi']),
    (r'(power|volume)\s*(button|flex|key)|\bside\s*key\b', ['Buttons Not Working (Power / Volume)',
                                                           'Crown / Button Not Working'], []),
    (r'\bhome\s*button\b', ['Home Button Not Working'], ['Mobile Phone', 'Tablet']),
    (r'fingerprint|touch\s*id|face\s*id', ['Fingerprint / Face Unlock Not Working'], []),
    (r'\bhinge', ['Hinge Damaged'], ['Laptop']),
    (r'keyboard\s*(module|replacement)|laptop\s*keyboard', ['Keyboard Not Working / Keys Damaged'], ['Laptop']),
    (r'\b(trackpad|touchpad)\b', ['Trackpad / Mouse Not Working'], ['Laptop']),
    (r'\b(ssd|nvme|hdd|hard\s*(disk|drive))\b', ['Hard Disk / SSD Issue', 'Slow Performance / Hanging',
                                                  'Storage Full / Insufficient'], ['Laptop', 'Desktop']),
    (r'\b(ram|ddr\d|so-?dimm|memory\s*module)\b', ['RAM Issue', 'Slow Performance / Hanging'],
     ['Laptop', 'Desktop']),
    (r'\b(motherboard|mainboard|logic\s*board)\b|\b[abhxz]\d{3}m?\b', ['Motherboard Issue', 'Short Circuit'],
     ['Desktop']),
    (r'power\s*supply|\bpsu\b|\b([4-9]\d{2}|1\d{3})\s*w\b',
     ['Power Supply (PSU) Failure', 'Device Not Turning On (Dead)', 'Random Restart / Auto Reboot'], ['Desktop']),
    (r'\b(geforce|radeon|rtx|gtx)\b|graphics\s*card', ['Graphics Card / GPU Failure', 'No Display Output'],
     ['Desktop']),
    (r'\b(fan|heatsink|thermal\s*paste|aio)\b|\bcpu\s*cooler\b|\b(h100i|nh-d15|hyper\s*212)\b',
     ['Fan Noise / Cooling Issue', 'Device Overheating', 'Dust Cleaning / Thermal Paste'], ['Laptop', 'Desktop']),
    (r'\busb\s*(port|board)\b', ['USB Port Not Working'], []),
    (r'\b(hdmi|displayport)\b', ['HDMI / Display Port Issue'], ['Laptop', 'Desktop']),
    (r'\b(lan|ethernet|network\s*card)\b', ['Network Card / Ethernet Issue'], ['Desktop']),
    (r'\b(toner|cartridge|ink)\b', ['Toner / Ink Cartridge Issue', 'Poor Print Quality / Faded',
                                    'Streaks / Lines on Print'], ['Printer']),
    (r'\bdrum\b', ['Drum Unit Replacement', 'Streaks / Lines on Print'], ['Printer']),
    (r'print\s*head', ['Print Head Clogged / Damaged', 'Poor Print Quality / Faded'], ['Printer']),
    (r'(paper|pickup)\s*(feed|tray|roller)|\bfuser\b', ['Paper Feeder / Tray Issue', 'Paper Jam'], ['Printer']),
    (r'\bstrap\b|\bwatch\s*band\b', ['Watch Band / Strap Broken'], ['Smartwatch']),
    (r'\b(stylus|pencil)\b', ['Stylus / Apple Pencil Not Working'], ['Tablet']),
]

# a device type named in the part's name wins over the rule's own
PART_DEVICES = [
    (r'\b(laptop|notebook|macbook|chromebook)\b|\b1[345]\.\d\b', 'Laptop'),
    (r'\b(iphone|phone|mobile|redmi|pixel|oneplus|vivo|oppo|realme|xiaomi)\b|\bgalaxy\s*[asmz]\d', 'Mobile Phone'),
    (r'\b(ipad|tablet)\b|\bgalaxy\s*tab\b', 'Tablet'),
    (r'\bwatch\b', 'Smartwatch'),
    (r'\b(printer|laserjet|deskjet)\b', 'Printer'),
    (r'\b(desktop|pcie|atx|matx)\b', 'Desktop'),
    (r'\b(router|mesh|access\s*point)\b', 'Networking & Wi-Fi'),
]

# whole devices, accessories and test items are not parts
NOT_A_PART = (r'\b(arm|mount|stand|backpack|bag|plate|kettle|banana|test|demo|pack|kit|build|barebone|nuc|'
              r'headphones?|headset|earbuds|power\s*bank|ups|surge)\b')


def guess_part(name):
    """(problem names, device type names) for a spare part's name; ([], []) when nothing matches."""
    text = (name or '').lower()
    if not text or re.search(NOT_A_PART, text):
        return [], []
    problems, devices = [], []
    for pattern, names, default in PART_RULES:
        if re.search(pattern, text):
            problems += [n for n in names if n not in problems]
            devices += [d for d in default if d not in devices]
    if not problems:
        return [], []
    named = [device for pattern, device in PART_DEVICES if re.search(pattern, text)]
    return problems, named or devices


def fill_part_problems(env):
    """Spare parts without problems get them (and the device types they fit) from their names."""
    Template = env['product.template'].with_context(active_test=False)
    Issue = env['job.card.issue.type'].with_context(active_test=False)
    Category = env['device.category'].with_context(active_test=False)
    issues = {i.name.lower(): i for i in Issue.search([])}
    cats = {c.name: c for c in Category.search([])}
    filled = 0
    for part in Template.search([('type', '=', 'consu'), ('repair_issue_type_ids', '=', False)]):
        problems, devices = guess_part(part.name)
        found = Issue.browse([issues[n.lower()].id for n in problems if n.lower() in issues])
        wanted = Category.browse([cats[d].id for d in devices if d in cats])
        if wanted:
            # only those device types' problems: a laptop screen is not "Touch not working"
            found = found.filtered(lambda i: not i.device_category_ids or i.device_category_ids & wanted)
        if not found:
            continue
        vals = {'repair_issue_type_ids': [(6, 0, found.ids)]}
        if wanted and not part.fit_category_ids:
            vals['fit_category_ids'] = [(6, 0, wanted.ids)]
        part.write(vals)
        filled += 1
    _logger.info('369ai_fix: problems set on %d spare parts', filled)
    return filled
