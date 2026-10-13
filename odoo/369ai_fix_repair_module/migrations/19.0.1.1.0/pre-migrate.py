"""19.0.1.0.0 -> 19.0.1.1.0 (slim version): remove the first version's own app menus,
actions and views before the new views load. They use fields this version no longer
has, and Odoo validates them before it clears obsolete records."""
from odoo import SUPERUSER_ID, api

OLD = [
    # menus (children first), then actions, then views
    'menu_369ai_fix_issue_types', 'menu_369ai_fix_models', 'menu_369ai_fix_series', 'menu_369ai_fix_brands',
    'menu_369ai_fix_device_categories', 'menu_369ai_fix_settings', 'menu_369ai_fix_configuration',
    'menu_repair_service_prices', 'menu_repair_products', 'menu_369ai_fix_root',
    'action_repair_products', 'action_repair_service_price',
    'view_job_card_form_repair_prices', 'res_config_settings_view_form_repair_pricing',
    'product_template_form_view_repair', 'view_repair_product_list', 'view_repair_product_search',
    'view_repair_service_price_list', 'view_repair_service_price_form', 'view_repair_service_price_search',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in OLD:
        record = env.ref('369ai_fix_repair_module.%s' % name, raise_if_not_found=False)
        if record:
            record.unlink()
    # The Repair Prices model is gone; Odoo removes its metadata but not its table.
    cr.execute('DROP TABLE IF EXISTS repair_service_price')
