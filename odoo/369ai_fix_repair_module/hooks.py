"""Install-time data: device categories the website offers, their brands and models,
and one IT & Mobile Repair service per website repair (price 0). Runs once, on install
only, so prices edited in Odoo are never overwritten. Existing records are matched by
name or internal reference and left as they are."""
import base64
import json
import logging

from odoo.tools import file_open

_logger = logging.getLogger(__name__)

MODULE = '369ai_fix_repair_module'


def post_init_hook(env):
    with file_open(f'{MODULE}/data/seed_repairs.json') as f:
        seed = json.load(f)
    _ensure_visit_fee_product(env)
    tax = _vat_included_tax(env)
    created = 0
    for cat in seed['categories']:
        category = _category(env, cat['odoo_category'])
        for brand in cat['brands']:
            _brand_with_models(env, category, brand['name'], brand['models'])
        for repair in cat['repairs']:
            created += _repair_service(env, category, repair, tax)
    _logger.info('%s: %d repair services created', MODULE, created)
    run_data_fixes(env)


def run_data_fixes(env):
    """Shared by the install hook and the 19.0.1.2.0 upgrade: device tree clean-up,
    issue types per device, and issue types on the website's repair services."""
    from .device_tree import fix_device_tree
    from .issue_types import fill_issue_types, import_ai_issue_types
    fix_device_tree(env)
    import_ai_issue_types(env)
    fill_issue_types(env)


def _category(env, name):
    Category = env['device.category'].with_context(active_test=False)
    category = Category.search([('name', '=ilike', name)], limit=1)
    if not category:
        category = Category.create({'name': name})
        _logger.info('%s: device category %s created', MODULE, name)
    return category


def _brand_with_models(env, category, name, models):
    """Brand names are unique in mobile_repair: an existing brand is reused as it is."""
    Brand = env['device.brand'].with_context(active_test=False)
    brand = Brand.search([('name', '=ilike', name)], limit=1)
    if not brand:
        brand = Brand.create({'name': name, 'category_id': category.id})
    Series = env['device.series'].with_context(active_test=False)
    series = Series.search([('brand_id', '=', brand.id), ('name', '=ilike', name)], limit=1)
    if not series:
        series = Series.create({'name': name, 'brand_id': brand.id})
    Model = env['device.model'].with_context(active_test=False)
    have = {n.lower() for n in Model.search([('series_id', '=', series.id)]).mapped('name')}
    Model.create([{'name': m, 'series_id': series.id} for m in models if m.lower() not in have])


def _repair_service(env, category, repair, tax):
    Template = env['product.template'].with_context(active_test=False)
    if Template.search_count([('default_code', '=', repair['default_code'])]):
        return 0
    vals = {
        'name': repair['name'],
        'default_code': repair['default_code'],
        'type': 'service',
        'sale_ok': True,
        'purchase_ok': False,
        'list_price': 0.0,
        'categ_id': env.ref(f'{MODULE}.product_category_repair_services').id,
        'repair_category_ids': [(6, 0, category.ids)],
    }
    if tax:
        vals['taxes_id'] = [(6, 0, tax.ids)]
    if repair['photo']:
        try:
            with file_open(f"{MODULE}/static/seed/{repair['photo']}", 'rb') as f:
                vals['image_1920'] = base64.b64encode(f.read())
        except FileNotFoundError:
            _logger.warning('%s: photo %s missing', MODULE, repair['photo'])
    Template.create(vals)
    return 1


def _vat_included_tax(env):
    """The company's 5% sales tax with the price included, if there is one."""
    taxes = env['account.tax'].search([
        ('type_tax_use', '=', 'sale'),
        ('amount_type', '=', 'percent'),
        ('amount', '=', 5.0),
        ('company_id', '=', env.company.id),
    ])
    tax = taxes.filtered('price_include')[:1]
    if not tax:
        _logger.warning('%s: no 5%% price-included sales tax in %s; repair services keep the default '
                        'taxes. Set a price-included VAT on them so the price is what the customer pays.',
                        MODULE, env.company.name)
    return tax


def _ensure_visit_fee_product(env):
    """The visit fee is mobile_repair's Inspection Charge Product; create one if none is set."""
    params = env['ir.config_parameter'].sudo()
    current = params.get_param('mobile_repair.inspection_charge_product_id')
    if current and str(current).isdigit() and env['product.product'].browse(int(current)).exists():
        return
    Product = env['product.product'].with_context(active_test=False)
    product = Product.search([('default_code', '=', 'REPAIR-VISIT')], limit=1)
    if not product:
        product = Product.create({
            'name': 'Inspection / Visit Fee',
            'default_code': 'REPAIR-VISIT',
            'type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
            'list_price': 0.0,
            'categ_id': env.ref(f'{MODULE}.product_category_repair_services').id,
        })
    params.set_param('mobile_repair.inspection_charge_product_id', product.id)
