-- Merge the six old 369 ai Fix add-ons into one add-on, 369ai_fix, keeping all data.
--
-- Until October 2026 the service was six add-ons: 369ai_fix_customer_module,
-- 369ai_fix_repair_module, 369ai_fix_field_service, 369ai_fix_web_booking,
-- 369ai_fix_website_content and 369ai_fix_app. Their code is now this add-on's folders.
-- This script renames their records in the database to the new add-on, so the upgrade
-- finds everything (bookings, prices, pictures, settings, status messages) in place
-- instead of creating it again.
--
-- Run ONCE per database, with Odoo stopped, BEFORE `odoo-bin -u 369ai_fix`:
--   psql -h <host> -U <user> -d <db> -v ON_ERROR_STOP=1 -f merge_old_modules.sql
-- It works when only some of the old add-ons are installed (e.g. only the customer one);
-- the upgrade's migrations/19.0.2.0.0 then loads the data of the parts that were missing.
-- Everything happens in one transaction: on any error nothing is changed.
BEGIN;

DO $$
DECLARE
    old_names text[] := ARRAY['369ai_fix_customer_module', '369ai_fix_repair_module',
                              '369ai_fix_field_service', '369ai_fix_web_booking',
                              '369ai_fix_website_content', '369ai_fix_app'];
    keep_id integer;
    old_ids integer[];
    clash text;
BEGIN
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name = '369ai_fix') THEN
        RAISE EXCEPTION '369ai_fix is already in this database: nothing to merge';
    END IF;

    -- The module row that is kept and renamed: the first installed old add-on.
    SELECT id INTO keep_id FROM ir_module_module
     WHERE name = ANY (old_names) AND state IN ('installed', 'to upgrade')
     ORDER BY array_position(old_names, name::text) LIMIT 1;
    IF keep_id IS NULL THEN
        RAISE EXCEPTION 'none of the old 369 ai Fix add-ons is installed in this database';
    END IF;
    SELECT array_agg(id) INTO old_ids FROM ir_module_module WHERE name = ANY (old_names);

    -- Record IDs. Each old add-on that extended a model (job.card, online.service.order...)
    -- has its own copy of that model's and its fields' record IDs, all pointing at the same
    -- record. Keep one copy of each; a name pointing at two different records stops here.
    SELECT name INTO clash FROM ir_model_data
     WHERE module = ANY (old_names)
     GROUP BY name HAVING count(DISTINCT (model, res_id)) > 1 LIMIT 1;
    IF clash IS NOT NULL THEN
        RAISE EXCEPTION 'record id "%" points at different records in two old add-ons', clash;
    END IF;
    DELETE FROM ir_model_data d USING ir_model_data k
     WHERE d.module = ANY (old_names) AND k.module = ANY (old_names)
       AND d.name = k.name AND d.id > k.id;
    UPDATE ir_model_data SET module = '369ai_fix' WHERE module = ANY (old_names);

    -- SQL constraints and many2many tables are owned through the module row.
    UPDATE ir_model_constraint SET module = keep_id WHERE module = ANY (old_ids);
    UPDATE ir_model_relation SET module = keep_id WHERE module = ANY (old_ids);

    -- Dependencies: the old add-ons' own rows go (the new manifest lists its own);
    -- add-ons that depended on an old one (danatfix_repair_booking) now depend on 369ai_fix.
    DELETE FROM ir_module_module_dependency WHERE module_id = ANY (old_ids);
    UPDATE ir_module_module_dependency SET name = '369ai_fix' WHERE name = ANY (old_names);
    DELETE FROM ir_module_module_dependency a USING ir_module_module_dependency b
     WHERE a.name = '369ai_fix' AND b.name = '369ai_fix'
       AND a.module_id = b.module_id AND a.id > b.id;

    -- base.module_<name> record IDs of the module rows.
    DELETE FROM ir_model_data
     WHERE module = 'base' AND model = 'ir.module.module'
       AND res_id = ANY (old_ids) AND res_id <> keep_id;
    UPDATE ir_model_data SET name = 'module_369ai_fix'
     WHERE module = 'base' AND model = 'ir.module.module' AND res_id = keep_id;

    -- The module rows themselves (anything still linked to the removed rows cascades).
    DELETE FROM ir_module_module WHERE id = ANY (old_ids) AND id <> keep_id;
    UPDATE ir_module_module SET name = '369ai_fix', state = 'installed' WHERE id = keep_id;

    RAISE NOTICE '369ai_fix: merged % old add-on(s) into module row %', array_length(old_ids, 1), keep_id;
END $$;

COMMIT;
