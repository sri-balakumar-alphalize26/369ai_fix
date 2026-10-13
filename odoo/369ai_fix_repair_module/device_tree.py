"""Put every series under the right device category.

mobile_repair's sample data files phones, tablets and watches under brands that sit
in Laptop (Laptop > Apple holds iPhone 7-16, iPad and Apple Watch; Laptop > Samsung
holds Galaxy S/A/Z and Galaxy Tab; Huawei, Honor, Motorola... are mostly phones).
A job card only offers the brands of its category, so Mobile Phone > Apple > iPhone 13
cannot be picked. This moves each series under a brand of the same name in the right
category, merging into an existing series of the same name. Model ids are kept;
job cards and products that point at a moved series follow it.
"""
import logging
import re

_logger = logging.getLogger(__name__)

# Checked in this order: the first category whose keyword matches wins, so
# "MatePad" is a tablet and "MateBook" a laptop before "Mate" reads as a phone.
# Keywords match whole words only.
KEYWORDS = [
    ('Smartwatch', [
        'watch', 'garmin', 'fenix', 'forerunner', 'venu', 'amazfit', 'gtr', 'gts', 't-rex',
    ]),
    ('Tablet', [
        'ipad', 'galaxy tab', 'xiaomi pad', 'redmi pad', 'oneplus pad', 'oppo pad', 'vivo pad',
        'realme pad', 'pixel tablet', 'matepad', 'honor pad', 'lenovo tab', 'tab m11', 'tab p12',
        'yoga tab', 'surface pro', 'surface go', 'tablet',
    ]),
    ('Desktop', [
        'imac', 'mac mini', 'mac studio', 'mac pro', 'optiplex', 'elitedesk', 'prodesk',
        'thinkcentre', 'ideacentre', 'thinkstation', 'precision tower', 'veriton',
        'expertcenter', 'rog desktop', 'z workstation', 'desktop', 'all-in-one',
    ]),
    ('Laptop', [
        'macbook', 'macbook air', 'macbook pro', 'thinkpad', 'ideapad', 'legion', 'thinkbook',
        'latitude', 'inspiron', 'xps', 'vostro', 'precision', 'alienware', 'pavilion', 'envy',
        'spectre', 'elitebook', 'probook', 'victus', 'omen', 'zbook', 'vivobook', 'zenbook',
        'rog strix', 'rog zephyrus', 'rog flow', 'tuf gaming', 'proart', 'expertbook',
        'chromebook', 'aspire', 'swift', 'nitro', 'predator', 'travelmate', 'conceptd',
        'stealth', 'raider', 'titan', 'creator', 'prestige', 'modern', 'katana', 'thin',
        'cyborg', 'crosshair', 'summit', 'vector', 'surface laptop', 'surface book',
        'galaxy book', 'matebook', 'magicbook', 'gram', 'aorus', 'aero', 'g5', 'g7',
        'razer blade', 'razer book', 'framework', 'toughbook', 'tecra', 'portege',
        'satellite pro', 'inbook', 'megabook', 'laptop', 'g series gaming',
    ]),
    ('Mobile Phone', [
        'iphone', 'galaxy s21', 'galaxy s22', 'galaxy s23', 'galaxy s24', 'galaxy s25',
        'galaxy z', 'galaxy z flip', 'galaxy z fold', 'galaxy a', 'galaxy m', 'galaxy f',
        'mate 60', 'mate 70', 'mate x', 'nova', 'pura', 'p60', 'huawei enjoy', 'enjoy',
        'honor 200', 'honor x', 'magic 6', 'magic 7', 'magic v', 'moto', 'moto g', 'moto e',
        'edge', 'razr', 'thinkphone', 'nothing phone', 'cmf phone', 'camon', 'phantom',
        'spark', 'pova', 'pop', 'hot', 'note', 'smart', 'zero', 'gt 20', 'pixel', 'xperia',
        'zenfone', 'phone',
    ]),
]
MANAGED = [name for name, _words in KEYWORDS]
_PATTERNS = [(name, [re.compile(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(w)) for w in words])
             for name, words in KEYWORDS]


def classify(series_name):
    """The category name a series belongs to, or None when nothing matches."""
    text = (series_name or '').lower()
    for name, patterns in _PATTERNS:
        if any(p.search(text) for p in patterns):
            return name
    return None


def fix_device_tree(env, dry_run=False):
    """Move misfiled series. Returns the list of moves as dicts; with dry_run nothing
    is written (brands that would be created are reported as 'new')."""
    Category = env['device.category'].with_context(active_test=False)
    Brand = env['device.brand'].with_context(active_test=False)
    Series = env['device.series'].with_context(active_test=False)
    Model = env['device.model'].with_context(active_test=False)
    cats = {c.name: c for c in Category.search([('name', 'in', MANAGED)])}
    moves = []
    for series in Series.search([('brand_id.category_id.name', 'in', MANAGED)], order='id'):
        brand = series.brand_id
        target_name = classify(series.name)
        if not target_name or target_name == brand.category_id.name or target_name not in cats:
            continue
        target = cats[target_name]
        target_brand = Brand.search([('name', '=ilike', brand.name), ('category_id', '=', target.id)], limit=1)
        twin = Series.search([('brand_id', '=', target_brand.id), ('name', '=ilike', series.name)],
                             limit=1) if target_brand else Series.browse()
        moves.append({
            'series': series.name,
            'models': len(series.model_ids),
            'from': '%s > %s' % (brand.category_id.name, brand.name),
            'to': '%s > %s%s' % (target_name, brand.name, '' if target_brand else ' (new)'),
            'merge': bool(twin),
        })
        if dry_run:
            continue
        if not target_brand:
            target_brand = Brand.create({'name': brand.name, 'category_id': target.id})
        if twin:
            have = {m.name.strip().lower(): m for m in twin.model_ids}
            for model in series.model_ids:
                keep = have.get((model.name or '').strip().lower())
                if keep:
                    _repoint(env, 'model', model, keep)
                    model.active = False
                else:
                    model.series_id = twin
            _repoint(env, 'series', series, twin)
            series.active = False
            moved_to = twin
        else:
            series.brand_id = target_brand
            moved_to = series
        # Whatever pointed at this series now names the new brand and category.
        env['job.card'].sudo().search([('series_id', '=', moved_to.id)]).write({
            'brand_id': target_brand.id, 'device_category_id': target.id})
        env['product.template'].sudo().with_context(active_test=False).search(
            [('device_series_id', '=', moved_to.id)]).write({'device_brand_id': target_brand.id})
    if not dry_run and moves:
        _logger.info('369ai_fix_repair_module: %d series moved to the right category: %s', len(moves),
                     '; '.join('%s: %s -> %s%s' % (m['series'], m['from'], m['to'],
                                                   ' (merged)' if m['merge'] else '') for m in moves))
    return moves


def _repoint(env, kind, old, new):
    """Job cards and products that use `old` (a series or a model) use `new` instead."""
    if kind == 'model':
        env['job.card'].sudo().search([('model_id', '=', old.id)]).write({'model_id': new.id})
        env['product.template'].sudo().with_context(active_test=False).search(
            [('device_model_id', '=', old.id)]).write({'device_model_id': new.id})
    else:
        env['job.card'].sudo().search([('series_id', '=', old.id)]).write({'series_id': new.id})
        env['product.template'].sudo().with_context(active_test=False).search(
            [('device_series_id', '=', old.id)]).write({'device_series_id': new.id})
