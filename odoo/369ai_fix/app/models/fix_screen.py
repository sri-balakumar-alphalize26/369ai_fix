# -*- coding: utf-8 -*-
"""The green screens: one engine that draws every menu of the 369 ai Fix and Fix Website
apps in the Booking Desk's look, instead of Odoo's list, form and dialog.

A screen is a config in fix_screen_configs.SCREENS (model, filters, columns, the record's
sections, its buttons); a pop-up is a config in POPUPS (a wizard's fields and buttons).
The web client (static/src/app/screen/) asks only these methods:

* `screen_meta(key)`                    - the config + field labels/types/choices
* `screen_list(key, ...)`               - rows of the list (table, board or week)
* `screen_record(key, id)`              - one record: values, lines, buttons, notes
* `screen_save(key, id, values)`        - write / create, only the fields the config lists
* `screen_line(key, id, field, ...)`    - add / change / remove / reorder one line
* `screen_button(key, id, name)`        - one of the config's buttons
* `screen_pick(key, field, query, ...)` - choices for a many2one / many2many picker
* `screen_note(key, id, body)`          - a note in the record's chatter
* `screen_popup_open(action)` / `screen_popup_submit(...)` - a wizard as a green pop-up
* `screen_checks(visit_id, ...)` / `screen_result(visit_id, ...)` - "Before you start" and
  "What did you find?", through the technician page's own steps (visits/)

Everything runs as the user: access rights and record rules apply as in Odoo's own
screens. Only fields and buttons named in a config can be read, written or pressed. Each
button calls the same method Odoo's form calls, and each wizard is created and its
button pressed as Odoo would, so no business rule is copied here.
"""
import ast
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.addons.web.controllers.utils import clean_action

from .fix_screen_configs import MODEL_SCREENS, POPUPS, SCREENS, screen_tokens

PAGE = 40
TABLE_PAGE = 100
BIG_PAGE = 300          # board and week views show everything in their window
PICK_LIMIT = 12
NOTES = 30
# Never sent to the browser, whatever a config says.
SECRET = {'upload_token_hash', 'slot_token_hash', 'tech_token_hash', 'password', 'password_crypt'}
BINARY = ('binary', 'image')
RELATIONAL = ('many2one', 'many2many', 'one2many')


def _field_names(cfg):
    """Every field of the screen's model the config uses."""
    names = set(cfg.get('columns') or [])
    names |= set(cfg.get('search') or [])
    names.update(x for x in (cfg.get('title_field'), cfg.get('subtitle'), cfg.get('badge'), cfg.get('board'),
                             cfg.get('week'), cfg.get('group_by'), cfg.get('image')) if x)
    for section in cfg.get('sections') or []:
        names |= set(section.get('fields') or [])
        names |= set(section.get('info') or [])
        if section.get('lines'):
            names.add(section['lines'])
    names |= set(cfg.get('create_fields') or [])
    names |= set(cfg.get('watch') or [])
    return names - SECRET


def _editable(cfg):
    """Fields the screen may write: the sections' fields (not info), the table's columns,
    the create pop-up's fields."""
    names = set(cfg.get('create_fields') or [])
    if cfg.get('kind') == 'table':
        names |= set(cfg.get('columns') or [])
    for section in cfg.get('sections') or []:
        names |= set(section.get('fields') or [])
    return (names - set(cfg.get('readonly') or [])) - SECRET


def _domain(value):
    if isinstance(value, str):
        return ast.literal_eval(value)
    return list(value or [])


class FixScreen(models.AbstractModel):
    _name = 'fix.screen'
    _description = '369 ai Fix: green screens'

    # ------------------------------------------------------------------ config
    @api.model
    def _screen(self, key):
        cfg = SCREENS.get(key)
        if not cfg:
            raise UserError(_("Unknown screen: %s", key))
        user = self.env.user
        groups = cfg.get('groups')
        if groups and not any(user.has_group(g) for g in groups.split(',')):
            raise AccessError(_("You do not have access to %s.", cfg['title']))
        if cfg['model'] not in self.env:
            raise UserError(_("%s needs an add-on that is not installed.", cfg['title']))
        # sections only some people see (e.g. the arrival code) are left out for the others,
        # so their fields are neither sent nor written
        sections = [s for s in cfg.get('sections') or []
                    if not s.get('groups') or any(user.has_group(g) for g in s['groups'].split(','))]
        return dict(cfg, key=key, sections=sections)

    @api.model
    def screen_single(self, key):
        """The one record of a 'single' screen (e.g. Booking Desk Settings)."""
        cfg = self._screen(key)
        rec = getattr(self.env[cfg['model']], cfg['single'])()
        return rec.id

    @api.model
    def _model(self, cfg):
        Model = self.env[cfg['model']]
        if cfg.get('active_test') is False or 'active' in (cfg.get('columns') or []):
            Model = Model.with_context(active_test=False)
        return Model.with_context(**(cfg.get('context') or {}))

    @api.model
    def _fields_meta(self, Model, names):
        names = [n for n in names if n in Model._fields and n not in SECRET]
        meta = Model.fields_get(names, ['string', 'type', 'selection', 'relation', 'required',
                                        'readonly', 'help', 'digits'])
        for name, info in meta.items():
            field = Model._fields[name]
            if info['type'] == 'image' or getattr(field, 'type', '') == 'image':
                info['type'] = 'image'
            if info['type'] == 'monetary':
                info['type'] = 'float'
        return meta

    @api.model
    def _sections_meta(self, cfg, Model):
        """The line tables' own fields (labels, types) per one2many."""
        lines = {}
        for section in cfg.get('sections') or []:
            fname = section.get('lines')
            if fname and fname in Model._fields:
                Line = self.env[Model._fields[fname].comodel_name]
                lines[fname] = self._fields_meta(Line, section.get('columns') or [])
        return lines

    @api.model
    def screen_meta(self, key):
        cfg = self._screen(key)
        Model = self._model(cfg)
        Model.check_access('read')
        meta = self._fields_meta(Model, _field_names(cfg))
        can_write = Model.has_access('write')
        can_create = Model.has_access('create') and cfg.get('create', False)
        user = self.env.user
        buttons = [dict(b) for b in cfg.get('buttons') or []
                   if not b.get('groups') or any(user.has_group(g) for g in b['groups'].split(','))]
        for button in buttons:
            button.pop('show', None)
            button.pop('groups', None)
        return {
            'key': key,
            'title': cfg['title'],
            'icon': cfg.get('icon', 'fa-list'),
            'hint': cfg.get('hint', ''),
            'kind': cfg.get('kind', 'records'),
            'model': cfg['model'],
            'columns': [c for c in cfg.get('columns') or [] if c in meta],
            'filters': [{'key': f['key'], 'label': f['label']} for f in cfg.get('filters') or []],
            'default_filter': cfg.get('default_filter') or '',
            'modes': cfg.get('modes') or ['table'],
            'board': cfg.get('board') or '',
            'week': cfg.get('week') or '',
            'group_by': cfg.get('group_by') or '',
            'title_field': cfg.get('title_field') or 'display_name',
            'widgets': cfg.get('widgets') or {},
            'tokens': screen_tokens(cfg.get('tokens')),
            'subtitle': cfg.get('subtitle') or '',
            'badge': cfg.get('badge') or '',
            'image': cfg.get('image') or '',
            'sections': cfg.get('sections') or [],
            'tabs': cfg.get('tabs') or [],
            'buttons': buttons,
            'create_fields': cfg.get('create_fields') or [],
            'create_confirm': bool(cfg.get('create_confirm')),
            'readonly': sorted(set(meta) - _editable(cfg)) if can_write else sorted(meta),
            'pick_domain': {k: v for k, v in (cfg.get('pick_domain') or {}).items()},
            'fields': meta,
            'lines': self._sections_meta(cfg, Model),
            'can_create': bool(can_create),
            'can_delete': bool(cfg.get('delete') and Model.has_access('unlink')),
            'can_write': bool(can_write),
            'sequence': bool(cfg.get('sequence') and 'sequence' in Model._fields),
            'notes': bool(cfg.get('notes') and 'message_ids' in Model._fields),
            'single': bool(cfg.get('single')),
            'record_screen': cfg.get('record_screen', ''),
        }

    # ------------------------------------------------------------------ values
    @api.model
    def _values(self, records, names):
        """Plain values for the browser: many2one [id, name], many2many [{id, name}],
        one2many ids, images as true/false (the browser loads /web/image)."""
        if not records:
            return []
        names = [n for n in names if n in records._fields and n not in SECRET]
        plain = [n for n in names if records._fields[n].type not in BINARY]
        wanted = list(dict.fromkeys(plain + ['write_date']))
        try:
            rows = records.with_context(bin_size=True).read(wanted)
        except AccessError:
            # e.g. "On hand" for someone without stock rights: those fields stay empty
            readable = []
            for name in wanted:
                try:
                    records[:1].with_context(bin_size=True).read([name])
                    readable.append(name)
                except AccessError:
                    continue
            rows = records.with_context(bin_size=True).read(readable)
            for row in rows:
                for name in set(wanted) - set(readable):
                    row[name] = False
        by_id = {row['id']: row for row in rows}
        binaries = [n for n in names if records._fields[n].type in BINARY]
        out = []
        for rec in records:
            row = by_id[rec.id]
            for name in plain:
                field = records._fields[name]
                value = row.get(name)
                if field.type == 'many2many':
                    row[name] = [{'id': r.id, 'name': r.display_name} for r in rec[name]]
                elif field.type == 'one2many':
                    row[name] = value or []
                elif field.type in ('date', 'datetime'):
                    row[name] = field.to_string(value) if value else False
                elif field.type == 'html':
                    row[name] = str(value or '')
            for name in binaries:
                row[name] = bool(rec.with_context(bin_size=True)[name])
            row['write_date'] = fields.Datetime.to_string(row['write_date']) if row.get('write_date') else ''
            row['display_name'] = rec.display_name
            out.append(row)
        return out

    @api.model
    def _incoming(self, Model, allowed, values):
        """Browser values -> ORM values, only for `allowed` fields."""
        vals = {}
        for name, value in (values or {}).items():
            if name not in allowed or name not in Model._fields:
                raise AccessError(_("The field %s cannot be changed here.", name))
            field = Model._fields[name]
            if field.type == 'many2one':
                vals[name] = int(value[0] if isinstance(value, (list, tuple)) else value or 0) or False
            elif field.type == 'many2many':
                ids = [int(v['id'] if isinstance(v, dict) else v) for v in (value or [])]
                vals[name] = [Command.set(ids)]
            elif field.type in BINARY:
                vals[name] = value or False
            elif field.type == 'one2many':
                raise AccessError(_("Lines are changed one by one."))
            else:
                vals[name] = value
        return vals

    @api.model
    def _record(self, cfg, rec_id):
        rec = self._model(cfg).browse(int(rec_id)).exists()
        if not rec:
            raise UserError(_("This record no longer exists."))
        rec.check_access('read')
        return rec

    # ------------------------------------------------------------------ list
    @api.model
    def _list_domain(self, cfg, query='', filter_key=None):
        domain = _domain(cfg.get('domain'))
        filters = {f['key']: f for f in cfg.get('filters') or []}
        chosen = filters.get(filter_key or '') or filters.get(cfg.get('default_filter') or '')
        if chosen:
            domain += self._filter_domain(chosen)
        query = (query or '').strip()
        search = cfg.get('search') or []
        if query and search:
            domain += ['|'] * (len(search) - 1) + [(name, 'ilike', query) for name in search]
        return domain

    @api.model
    def _filter_domain(self, chosen):
        domain = chosen.get('domain')
        if callable(domain):
            return domain(self.env)
        return _domain(domain)

    @api.model
    def screen_list(self, key, query='', filter=None, offset=0, mode='table', start=None):
        cfg = self._screen(key)
        Model = self._model(cfg)
        domain = self._list_domain(cfg, query, filter)
        limit = PAGE
        if mode == 'week' and cfg.get('week'):
            day = fields.Date.to_date(start) if start else fields.Date.context_today(self)
            day = day - timedelta(days=day.weekday())
            domain += [(cfg['week'], '>=', fields.Datetime.to_string(day)),
                       (cfg['week'], '<', fields.Datetime.to_string(day + timedelta(days=7)))]
            limit, offset = BIG_PAGE, 0
            start = fields.Date.to_string(day)
        elif mode == 'board':
            limit, offset = BIG_PAGE, 0
        elif cfg.get('kind') == 'table':
            limit = TABLE_PAGE
        records = Model.search(domain, offset=int(offset or 0), limit=limit, order=cfg.get('order'))
        names = set(cfg.get('columns') or [])
        names.update(x for x in (cfg.get('title_field'), cfg.get('subtitle'), cfg.get('badge'), cfg.get('board'),
                                 cfg.get('week'), cfg.get('group_by'), cfg.get('image')) if x)
        names |= set(cfg.get('watch') or [])
        if cfg.get('sequence') and 'sequence' in Model._fields:
            names.add('sequence')
        counts = {}
        for f in cfg.get('filters') or []:
            if f.get('count'):
                counts[f['key']] = Model.search_count(_domain(cfg.get('domain')) + self._filter_domain(f))
        return {
            'rows': self._values(records, names),
            'total': Model.search_count(domain),
            'offset': int(offset or 0),
            'limit': limit,
            'start': start or '',
            'counts': counts,
        }

    # ------------------------------------------------------------------ record
    @api.model
    def screen_record(self, key, rec_id):
        cfg = self._screen(key)
        if cfg.get('settings'):
            return self._settings_record(cfg)
        rec = self._record(cfg, rec_id)
        return self._record_view(cfg, rec)

    @api.model
    def _record_view(self, cfg, rec):
        data = self._values(rec, _field_names(cfg))[0]
        lines = {}
        for section in cfg.get('sections') or []:
            fname = section.get('lines')
            if fname and fname in rec._fields:
                sub = rec[fname]
                if 'sequence' in sub._fields:
                    sub = sub.sorted(lambda l: (l.sequence, l.id))
                lines[fname] = self._values(sub, section.get('columns') or [])
        user = self.env.user
        buttons = []
        for button in cfg.get('buttons') or []:
            if button.get('groups') and not any(user.has_group(g) for g in button['groups'].split(',')):
                continue
            show = button.get('show')
            if show is None or rec.filtered_domain(_domain(show)):
                buttons.append(button['name'])
        locked = bool(cfg.get('locked') and rec.filtered_domain(_domain(cfg['locked'])))
        return {
            'id': rec.id,
            'values': data,
            'lines': lines,
            'buttons': buttons,
            'locked': locked,
            'notes': self._notes(rec) if cfg.get('notes') else [],
            'extra': rec._fix_screen_extra(cfg['key']) if hasattr(rec, '_fix_screen_extra') else {},
        }

    @api.model
    def _notes(self, rec):
        if 'message_ids' not in rec._fields:
            return []
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', rec._name), ('res_id', '=', rec.id),
            ('message_type', 'in', ('comment', 'notification')),
        ], limit=NOTES, order='id desc')
        return [{
            'id': m.id,
            'author': m.author_id.name or (m.email_from or ''),
            'date': fields.Datetime.to_string(m.date),
            'body': str(m.body or ''),
            'note': m.subtype_id == self.env.ref('mail.mt_note', raise_if_not_found=False),
            'changes': [{'field': t.field_id.field_description or '', 'old': t.old_value_char or '',
                         'new': t.new_value_char or ''} for t in m.sudo().tracking_value_ids],
        } for m in messages if m.body or m.tracking_value_ids]

    @api.model
    def screen_save(self, key, rec_id, values, defaults=None, extra=None):
        """Write the record (or create it when `rec_id` is empty); returns the record view.
        `extra`: what the create question answered (e.g. who takes a day off's visits), handed to
        the screen's `after_create` method of the new record."""
        cfg = self._screen(key)
        if cfg.get('settings'):
            return self._settings_save(cfg, values)
        Model = self._model(cfg)
        allowed = _editable(cfg)
        vals = self._incoming(Model, allowed, values)
        if rec_id:
            rec = self._record(cfg, rec_id)
            if cfg.get('locked') and rec.filtered_domain(_domain(cfg['locked'])):
                raise UserError(_("This record is closed and cannot be changed here."))
            rec.write(vals)
        else:
            if not cfg.get('create'):
                raise AccessError(_("New records are not made here."))
            ctx = {'default_%s' % k: (v[0] if isinstance(v, (list, tuple)) and v and not isinstance(v[0], (list, tuple, dict)) else v)
                   for k, v in (defaults or {}).items() if k in Model._fields and k not in SECRET}
            ctx.update(cfg.get('create_context') or {})
            rec = Model.with_context(**ctx).create(vals)
            if cfg.get('after_create'):
                getattr(rec, cfg['after_create'])(extra if isinstance(extra, dict) else {})
        return self._record_view(cfg, rec)

    @api.model
    def screen_create_confirm(self, key, values, defaults=None):
        """What to ask before a new record of this screen is saved ('' = nothing to ask): the
        screen's `create_confirm` method on its model, given the values typed in the pop-up."""
        cfg = self._screen(key)
        method = cfg.get('create_confirm')
        if not method or not cfg.get('create'):
            return ''
        Model = self._model(cfg)
        Model.check_access('create')
        vals = self._incoming(Model, _editable(cfg), values)
        for k, v in (defaults or {}).items():
            if k in Model._fields and k not in SECRET:
                vals.setdefault(k, v[0] if isinstance(v, (list, tuple)) and v and not isinstance(v[0], (list, tuple, dict)) else v)
        return getattr(Model, method)(vals) or ''

    @api.model
    def screen_delete(self, key, rec_id):
        cfg = self._screen(key)
        if not cfg.get('delete'):
            raise AccessError(_("Records are not deleted here."))
        self._record(cfg, rec_id).unlink()
        return True

    @api.model
    def screen_resequence(self, key, ids):
        cfg = self._screen(key)
        Model = self._model(cfg)
        if not cfg.get('sequence') or 'sequence' not in Model._fields:
            raise AccessError(_("This list has no order."))
        for index, rec in enumerate(Model.browse([int(i) for i in ids]).exists()):
            rec.sequence = (index + 1) * 10
        return True

    # ------------------------------------------------------------------ lines
    @api.model
    def screen_line(self, key, rec_id, field, op, line_id=None, values=None, ids=None):
        """One line of a line table: op = add | update | remove | order."""
        cfg = self._screen(key)
        section = next((s for s in cfg.get('sections') or [] if s.get('lines') == field), None)
        if not section or section.get('readonly'):
            raise AccessError(_("These lines are not changed here."))
        rec = self._record(cfg, rec_id)
        if cfg.get('locked') and rec.filtered_domain(_domain(cfg['locked'])):
            raise UserError(_("This record is closed and cannot be changed here."))
        Line = self.env[rec._fields[field].comodel_name]
        allowed = set(section.get('columns') or []) - set(section.get('line_readonly') or []) - SECRET
        current = rec[field]
        if op == 'add':
            vals = self._incoming(Line, allowed, values)
            vals.update(self._line_defaults(Line, vals))
            rec.write({field: [Command.create(dict(section.get('line_defaults') or {}, **vals))]})
        elif op == 'update':
            line = current.filtered(lambda l: l.id == int(line_id or 0))
            if not line:
                raise UserError(_("That line is gone."))
            vals = self._incoming(Line, allowed, values)
            if 'product_id' in vals:
                vals.update(self._line_defaults(Line, vals, refresh=True))
            rec.write({field: [Command.update(line.id, vals)]})
        elif op == 'remove':
            if not section.get('remove', True):
                raise AccessError(_("Lines are not removed here."))
            rec.write({field: [Command.delete(int(line_id or 0))]})
        elif op == 'order':
            if 'sequence' not in Line._fields:
                raise AccessError(_("These lines have no order."))
            keep = {l.id for l in current}
            rec.write({field: [Command.update(int(i), {'sequence': (n + 1) * 10})
                               for n, i in enumerate(ids or []) if int(i) in keep]})
        else:
            raise UserError(_("Unknown line change."))
        return self._record_view(cfg, rec)

    @api.model
    def _line_defaults(self, Line, vals, refresh=False):
        """What Odoo's onchange would fill when a product is chosen: price and description."""
        out = {}
        product = self.env['product.product'].browse(vals.get('product_id') or 0).exists()
        if not product:
            return out
        if 'unit_price' in Line._fields and (refresh or 'unit_price' not in vals):
            out.setdefault('unit_price', product.lst_price or product.standard_price)
        if 'description' in Line._fields and (refresh or not vals.get('description')):
            out.setdefault('description', product.display_name)
        return {k: v for k, v in out.items() if k not in vals}

    # ------------------------------------------------------------------ pickers
    @api.model
    def screen_pick(self, key, field, query='', values=None, line_field=None):
        cfg = self._screen(key)
        Model = self._model(cfg)
        if line_field:
            section = next((s for s in cfg.get('sections') or [] if s.get('lines') == line_field), None)
            if not section or field not in (section.get('columns') or []):
                raise AccessError(_("No such choice here."))
            Model = self.env[Model._fields[line_field].comodel_name]
            domain_cfg = (section.get('pick_domain') or {}).get(field)
        else:
            if field not in _editable(cfg) and field not in (cfg.get('search') or []):
                raise AccessError(_("No such choice here."))
            domain_cfg = (cfg.get('pick_domain') or {}).get(field)
        comodel = self.env[Model._fields[field].comodel_name]
        domain = []
        for leaf in _domain(domain_cfg):
            if isinstance(leaf, (list, tuple)) and isinstance(leaf[2], str) and leaf[2].startswith('$'):
                ref = (values or {}).get(leaf[2][1:])
                if isinstance(ref, (list, tuple)):
                    ref = ref[0] if ref else False
                domain.append((leaf[0], leaf[1], ref or False))
            else:
                domain.append(leaf)
        found = comodel.name_search(query or '', domain, limit=PICK_LIMIT)
        return [{'id': rid, 'name': name} for rid, name in found]

    @api.model
    def screen_options(self, key, field, line_field=None):
        """All choices of a small many2many (ticks), e.g. accessories."""
        cfg = self._screen(key)
        Model = self._model(cfg)
        if line_field:
            Model = self.env[Model._fields[line_field].comodel_name]
        comodel = self.env[Model._fields[field].comodel_name]
        return [{'id': r.id, 'name': r.display_name} for r in comodel.search([], limit=200)]

    # ------------------------------------------------------------------ notes
    @api.model
    def screen_note(self, key, rec_id, body):
        cfg = self._screen(key)
        rec = self._record(cfg, rec_id)
        body = (body or '').strip()
        if not body:
            raise UserError(_("Write the note first."))
        rec.message_post(body=body, subtype_xmlid='mail.mt_note')
        return self._notes(rec)

    # ------------------------------------------------------------------ buttons
    @api.model
    def screen_button(self, key, rec_id, name):
        cfg = self._screen(key)
        button = next((b for b in cfg.get('buttons') or [] if b['name'] == name), None)
        if not button:
            raise AccessError(_("This button is not on this screen."))
        if button.get('groups') and not any(self.env.user.has_group(g) for g in button['groups'].split(',')):
            raise AccessError(_("Only some people may use %s.", button['label']))
        if cfg.get('settings'):
            settings = self._settings_new(cfg)
            return self._outcome(getattr(settings, name)())
        rec = self._record(cfg, rec_id)
        if button.get('show') is not None and not rec.filtered_domain(_domain(button['show'])):
            raise UserError(_("%s is not possible now. Refresh the screen.", button['label']))
        method = button.get('method') or name
        if method.startswith('_') and not button.get('private_ok'):
            raise AccessError(_("This button is not on this screen."))
        result = getattr(rec, method)()
        return self._outcome(result, odoo=button.get('odoo'))

    # ------------------------------------------------------------------ what a button answered
    @api.model
    def _outcome(self, result, odoo=False):
        """{'done': True} | {'popup': ...} | {'open': {screen, id, defaults}} | {'action': ...}
        ('action' only for links, phone calls and what stays in Odoo, e.g. invoices)."""
        if not isinstance(result, dict) or result.get('type') in (None, 'ir.actions.act_window_close'):
            return {'done': True}
        if result.get('type') == 'ir.actions.client' and result.get('tag') == 'reload':
            return {'done': True}
        kind = result.get('type')
        if kind == 'ir.actions.act_url':
            return {'action': result}
        if kind == 'ir.actions.client':
            if result.get('tag') == 'display_notification':
                params = result.get('params') or {}
                return {'done': True, 'message': params.get('message') or params.get('title') or ''}
            return {'action': clean_action(result, self.env)}
        if kind != 'ir.actions.act_window' or odoo:
            return {'action': clean_action(result, self.env)}
        model = result.get('res_model')
        target = result.get('target')
        context = result.get('context') or {}
        if isinstance(context, str):
            try:
                context = ast.literal_eval(context)
            except (ValueError, SyntaxError):
                context = {}
        if target == 'new':
            popup = self._popup_for(result, context)
            if popup:
                return {'popup': popup}
            return {'action': clean_action(result, self.env)}
        screen = MODEL_SCREENS.get(model)
        if screen and screen in SCREENS:
            defaults = {}
            Target = self.env[model]
            for k, v in context.items():
                if not k.startswith('default_'):
                    continue
                name = k[8:]
                field = Target._fields.get(name)
                if field and field.type == 'many2one' and isinstance(v, int) and v:
                    v = [v, self.env[field.comodel_name].browse(v).display_name]
                defaults[name] = v
            res_id = result.get('res_id') or False
            domain = result.get('domain')
            if not res_id and domain and isinstance(domain, (list, tuple)):
                # "view the job cards / visits of ...": open the one record when there is one
                Model = self.env[model]
                found = Model.search(_domain(domain), limit=2)
                if len(found) == 1:
                    res_id = found.id
            return {'open': {'screen': screen, 'id': res_id, 'defaults': defaults,
                             'new': not res_id and bool(defaults)}}
        return {'action': clean_action(result, self.env)}

    # ------------------------------------------------------------------ pop-ups
    @api.model
    def _popup_for(self, action, context):
        model = action.get('res_model')
        res_id = action.get('res_id') or False
        if model == 'fix.service.visit' and res_id:
            checks = self.env.ref('369ai_fix.view_service_visit_checks_form', raise_if_not_found=False)
            views = action.get('views') or []
            if checks and any(v and v[0] == checks.id for v in views):
                return {'kind': 'checks', 'visit_id': res_id, 'title': action.get('name') or _("Before you start")}
        if model == 'fix.visit.result.wizard':
            return {'kind': 'result', 'visit_id': context.get('default_visit_id'),
                    'title': action.get('name') or _("What did you find?")}
        if model not in POPUPS or model not in self.env:
            return None
        return self._popup_view(model, res_id, context, action.get('name'))

    @api.model
    def _popup_view(self, model, res_id, context, title=None):
        cfg = POPUPS[model]
        Wizard = self.env[model].with_context(**self._safe_context(context))
        names = list(dict.fromkeys((cfg.get('fields') or []) + (cfg.get('info') or []) + (cfg.get('watch') or [])))
        meta = self._fields_meta(Wizard, names)
        if res_id:
            rec = Wizard.browse(int(res_id)).exists()
            values = self._values(rec, names)[0] if rec else {}
        else:
            # every field's default, as create() takes them: the order a wizard is for comes as
            # default_order_id and its other fields are computed from it
            defaults = Wizard.default_get(list(Wizard._fields))
            rec = Wizard.new(defaults)
            values = {}
            for name in names:
                if name not in Wizard._fields:
                    continue
                field = Wizard._fields[name]
                value = rec[name]
                if field.type == 'many2one':
                    values[name] = [value.id, value.display_name] if value else False
                elif field.type == 'many2many':
                    values[name] = [{'id': r.id, 'name': r.display_name} for r in value]
                elif field.type in ('date', 'datetime'):
                    values[name] = field.to_string(value) if value else False
                elif field.type in BINARY:
                    values[name] = bool(value)
                elif field.type == 'html':
                    values[name] = str(value or '')
                else:
                    values[name] = value
        options = {}
        for name in cfg.get('ticks') or []:
            comodel = self.env[Wizard._fields[name].comodel_name]
            options[name] = [{'id': r.id, 'name': r.display_name} for r in comodel.search([], limit=200)]
        user = self.env.user
        buttons = [{k: v for k, v in b.items() if k != 'groups'} for b in cfg.get('buttons') or []
                   if not b.get('groups') or any(user.has_group(g) for g in b['groups'].split(','))]
        return {
            'kind': 'form',
            'model': model,
            'res_id': res_id or False,
            'title': title or cfg.get('title') or '',
            'intro': cfg.get('intro', ''),
            'fields': cfg.get('fields') or [],
            'info': cfg.get('info') or [],
            'show': cfg.get('show') or {},
            'widgets': cfg.get('widgets') or {},
            'meta': meta,
            'values': values,
            'options': options,
            'buttons': buttons,
            'context': self._safe_context(context),
            'pick_domain': cfg.get('pick_domain') or {},
            'record': bool(cfg.get('record')),
        }

    @api.model
    def _safe_context(self, context):
        """The wizard's own context keys (defaults and its flags), nothing that changes who
        the user is or which company they work in."""
        blocked = {'uid', 'allowed_company_ids', 'su', 'active_test', 'lang', 'tz'}
        safe = {}
        for key, value in (context or {}).items():
            if not isinstance(key, str) or key in blocked:
                continue
            if isinstance(value, datetime):
                value = fields.Datetime.to_string(value)
            elif isinstance(value, date):
                value = fields.Date.to_string(value)
            if isinstance(value, (str, int, float, bool, list, type(None))):
                safe[key] = value
        return safe

    @api.model
    def screen_popup_pick(self, model, field, query='', values=None):
        """Choices for a pop-up's many2one / many2many (e.g. the technician on Approve)."""
        cfg = POPUPS.get(model)
        if not cfg or field not in (cfg.get('fields') or []):
            raise AccessError(_("No such choice here."))
        comodel = self.env[self.env[model]._fields[field].comodel_name]
        domain = []
        for leaf in _domain((cfg.get('pick_domain') or {}).get(field)):
            if isinstance(leaf, (list, tuple)) and isinstance(leaf[2], str) and leaf[2].startswith('$'):
                ref = (values or {}).get(leaf[2][1:])
                domain.append((leaf[0], leaf[1], (ref[0] if isinstance(ref, (list, tuple)) and ref else ref) or False))
            else:
                domain.append(leaf)
        return [{'id': rid, 'name': name} for rid, name in comodel.name_search(query or '', domain, limit=PICK_LIMIT)]

    @api.model
    def screen_popup_open(self, action):
        """A wizard action as a green pop-up, or {'action'} when it stays in Odoo."""
        return self._outcome(action)

    @api.model
    def screen_popup_submit(self, model, res_id, values, button, context=None):
        cfg = POPUPS.get(model)
        if not cfg:
            raise AccessError(_("Unknown pop-up."))
        spec = next((b for b in cfg.get('buttons') or [] if b['name'] == button), None)
        if not spec:
            raise AccessError(_("This button is not on this pop-up."))
        if spec.get('groups') and not any(self.env.user.has_group(g) for g in spec['groups'].split(',')):
            raise AccessError(_("Only some people may use %s.", spec['label']))
        ctx = self._safe_context(context)
        Wizard = self.env[model].with_context(**ctx)
        allowed = set(cfg.get('fields') or []) | set(cfg.get('hidden_fields') or [])
        vals = self._incoming(Wizard, allowed, values)
        if cfg.get('record'):
            rec = Wizard.browse(int(res_id or 0)).exists()
            if not rec:
                raise UserError(_("This record no longer exists."))
            if vals:
                rec.write(vals)
        elif res_id:
            rec = Wizard.browse(int(res_id)).exists()
            if not rec:
                raise UserError(_("This window expired. Open it again."))
            if vals:
                rec.write(vals)
        else:
            rec = Wizard.create(vals)
        if spec.get('save'):
            return {'done': True}
        return self._outcome(getattr(rec, button)())

    # ------------------------------------------------------------------ settings screens
    @api.model
    def _settings_new(self, cfg, values=None):
        Settings = self.env[cfg['model']]
        return Settings.create(values or {})

    @api.model
    def _settings_record(self, cfg):
        settings = self._settings_new(cfg)
        data = self._values(settings, _field_names(cfg))[0]
        return {'id': 0, 'values': data, 'lines': {}, 'buttons': [b['name'] for b in cfg.get('buttons') or []],
                'locked': False, 'notes': [], 'extra': {}}

    @api.model
    def _settings_save(self, cfg, values):
        # a new settings record starts from the current values; only the change is given
        Settings = self.env[cfg['model']]
        Settings.create(self._incoming(Settings, _editable(cfg), values)).execute()
        return self._settings_record(cfg)

    # ------------------------------------------------------------------ the two visit steps
    @api.model
    def _visit(self, visit_id):
        visit = self.env['fix.service.visit'].browse(int(visit_id or 0)).exists()
        if not visit:
            raise UserError(_("This visit no longer exists."))
        visit.check_access('write')
        return visit

    @api.model
    def screen_checks(self, visit_id, action=None, args=None):
        """'Before you start': the safety ticks, photos and video, then Start work."""
        visit = self._visit(visit_id)
        args = args or {}
        problem = None
        started = False
        if action:
            if action == 'start':
                visit.action_start_checked()
                started = True
            elif action == 'override':
                visit.write({'checks_override_reason': args.get('reason') or ''})
                visit.action_start_without_checks()
                started = True
            elif action.startswith('check_'):
                try:
                    with self.env.cr.savepoint():
                        problem = visit._vc_tech_act(action, item_id=args.get('item_id'), done=args.get('done'),
                                                     photo_id=args.get('photo_id'), data=args.get('data'),
                                                     name=args.get('name'))
                except (UserError, ValidationError):
                    problem = _("This file could not be read. Try another one.")
            else:
                raise UserError(_("Unknown action."))
        if visit.state == 'arrived':
            visit._vc_prepare()
        view = visit._vc_view() if visit.state == 'arrived' else None
        return {
            'name': visit.name,
            'state': visit.state,
            'started': started or visit.state != 'arrived',
            'view': view,
            'problem': problem,
            'is_manager': self.env.user.has_group('mobile_repair.group_mobile_repair_manager'),
            'photos': self._check_photos(visit) if view else {},
        }

    @api.model
    def _check_photos(self, visit):
        """Ids of the photos already taken, so the pop-up can show them."""
        visit = visit.sudo()
        return {
            'safety': visit.safety_photo_ids.filtered('image').ids,
            'sides': {str(p.id): bool(p.image) for p in visit.device_photo_ids},
        }

    @api.model
    def screen_result(self, visit_id, action=None, args=None):
        """'What did you find?': the same steps as the technician's page."""
        visit = self._visit(visit_id)
        extra, message = {}, None
        if action == 'result_parts':
            # searched as you type: the parts only, not the whole result each time
            if visit.state != 'in_progress':
                return {'parts': [], 'message': _("This is done while the work is in progress.")}
            return {'parts': visit._vr_parts((args or {}).get('query') or '')}
        if action:
            if visit.state != 'in_progress':
                message = _("This is done while the work is in progress.")
            else:
                try:
                    with self.env.cr.savepoint():
                        extra = visit._vr_tech_act(action, args or {}) or {}
                except UserError as err:
                    message = str(err)
        view = visit._vr_view() if visit.state == 'in_progress' else None
        return dict(extra, **{
            'name': visit.name,
            'state': visit.state,
            'view': view,
            'message': message,
            'result_label': (dict(visit._fields['check_result'].selection).get(visit.check_result, '')
                             if visit.check_result else ''),
        })

    # ------------------------------------------------------------------ the desk's notes tab
    @api.model
    def screen_notes(self, targets):
        """Notes of several records (booking, job cards, visit), newest first."""
        notes = []
        for key, rec_id in targets or []:
            cfg = self._screen(key)
            rec = self._record(cfg, rec_id)
            for note in self._notes(rec):
                notes.append(dict(note, where=rec.display_name, screen=key, rec_id=rec.id))
        notes.sort(key=lambda n: (n['date'] or '', n['id']), reverse=True)
        return notes[:60]
