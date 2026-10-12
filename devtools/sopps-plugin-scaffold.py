#!/usr/bin/env python3
"""
SOPS PluginNode scaffold — generate the Python backend + JS frontend skeleton
for a new SOPS custom plugin in one shot.

SOPS plugin files live in three places (auto-discovery vs. static serving are separate):
    Python backend (auto-discovery entry):
        {OUTDIR}/pipeline_plugins/components/collections/<system>/v1_0.py
    JS form source:
        {OUTDIR}/pipeline_plugins/components/static/components/atoms/<system>/<code>.js
    JS form (must go to Django STATIC_ROOT for the browser to load):
        {STATIC_ROOT}/components/atoms/<system>/<code>.js
    STATIC_ROOT is typically bk_sops/static (uwsgi maps /o/bk_sops/static → bk_sops/static).

Usage (interactive Q&A):
    python3 sopps-plugin-scaffold.py

Usage (CLI args; then bake into a new image — see SOPS_PLUGIN_SCAFFOLD.md):
    python3 sopps-plugin-scaffold.py \
        --code my_http_plugin \
        --name "My HTTP Plugin" \
        --system http \
        --outdir ./sops-plugins/code \
        --static-root ./sops-plugins/static \
        --schedule \
        --input url:string:"Target URL" --input timeout:int:"Timeout sec" \
        --output status_code:int:"HTTP Status"

The staging dirs mirror the container layout:
    {OUTDIR}/...        ->  /data/app/code/pipeline_plugins/...
    {STATIC_ROOT}/...   ->  /data/app/code/bk_sops/static/...

Typical Dockerfile.plugins (context = the staging parent dir):
    FROM <your bkce-sops base image>
    COPY --chown=apps:apps code/pipeline_plugins/ /data/app/code/pipeline_plugins/
    COPY --chown=apps:apps static/ /data/app/code/bk_sops/static/
"""

import argparse
import json
import os
import re
import sys

# ------------------------------------------------------------------ Templates

PY_TEMPLATE = '''# -*- coding: utf-8 -*-
"""SOPS PluginNode: {name} ({code})"""

from __future__ import absolute_import
import logging

from django.utils.translation import ugettext_lazy as _

from pipeline.conf import settings
from pipeline.component_framework.component import Component
from pipeline.core.flow.activity import Service{schedule_gen}
from pipeline.core.flow.io import StringItemSchema, IntItemSchema, BooleanItemSchema

__group_name__ = _("{system_label}")
logger = logging.getLogger(__name__)


class {service_class}(Service):
{schedule_block}
    def inputs_format(self):
        return [
{inputs_block}
        ]

    def outputs_format(self):
        return [
{outputs_block}
        ]

    def execute(self, data, parent_data):
        """Called when the node starts. Return True = success, False = retryable
        failure, raise = hard failure.

        Read input:  url = data.get_one_of_inputs('url')
        Write output: data.outputs.status_code = 200
        Globals:      parent_data.inputs
        """
        _ = self  # placeholder, avoid unused
        return True


class {component_class}(Component):
    name = _("{name}")
    code = "{code}"
    bound_service = {service_class}
    form = '%scomponents/atoms/{system}/{code}.js' % settings.STATIC_URL
'''

SCHEDULE_IMPORT = "\nfrom pipeline.core.flow.activity import Service, StaticIntervalGenerator"

SCHEDULE_BLOCK = '''
    __need_schedule__ = True
    interval = StaticIntervalGenerator(0)

    def schedule(self, data, parent_data, callback_data=None):
        """Polling mode: called repeatedly until self.finish_schedule() or
        self.schedule_fail(). interval in seconds."""
        return
'''

INPUT_TYPES = {
    'string': ('StringItemSchema', 'string'),
    'int':    ('IntItemSchema',    'int'),
    'bool':   ('BooleanItemSchema','bool'),
}


def _py_input(key, label, itype):
    sch_cls, py_type = INPUT_TYPES.get(itype, INPUT_TYPES['string'])
    return (
        "            self.InputItem(\n"
        "                name=_({label!r}),\n"
        "                key={key!r},\n"
        "                type={py_type!r},\n"
        "                schema={sch_cls}(description=_({label!r})),\n"
        "            ),"
    ).format(label=label, key=key, py_type=py_type, sch_cls=sch_cls)


def _py_output(key, label, itype):
    sch_cls, py_type = INPUT_TYPES.get(itype, INPUT_TYPES['string'])
    return (
        "            self.OutputItem(\n"
        "                name=_({label!r}),\n"
        "                key={key!r},\n"
        "                type={py_type!r},\n"
        "                schema={sch_cls}(description=_({label!r})),\n"
        "            ),"
    ).format(label=label, key=key, py_type=py_type, sch_cls=sch_cls)


# ------------------------------------------------------------------ JS template

JS_FIELD_TYPE = {
    'string': ('input', {'hookable': True}),
    'int':    ('int',   {'hookable': True}),
    'bool':   ('checkbox', {'hookable': True}),
}


def _js_field(key, label, itype):
    js_type, extras = JS_FIELD_TYPE.get(itype, JS_FIELD_TYPE['string'])
    attrs = {'name': label}
    attrs.update(extras)
    obj = {'tag_code': key, 'type': js_type, 'attrs': attrs}
    dumped = json.dumps(obj, ensure_ascii=False, indent=8)
    # json.dumps indents 8 spaces; we indent the whole block to 4
    return '        ' + dumped.replace('\n', '\n        ') + ','


JS_TEMPLATE = '''(function () {{
    $.atoms.{code} = [
{fields_block}
    ]
}})();
'''


# ------------------------------------------------------------------ Interactive + assembly

def _class_name(name):
    # "my plugin" -> "MyPlugin"; "http_request" -> "HttpRequest"
    return ''.join(p.capitalize() for p in re.split(r'[^A-Za-z0-9]', name) if p)


def _interactive():
    print("=== SOPS PluginNode Scaffold (interactive) ===\n")
    code = input("Plugin code (unique, lowercase+underscore, e.g. http_health_check): ").strip()
    if not re.match(r'^[a-z][a-z0-9_]*$', code):
        print("code must start with lowercase letter, contain only letters/digits/underscore"); sys.exit(1)
    name = input("Display name (e.g. HTTP Health Check): ").strip() or code
    system = input("System group dir (e.g. http / job / custom) [custom]: ").strip() or 'custom'
    system_label = input("Group display label (e.g. Custom Plugins) [Custom Plugins]: ").strip() or 'Custom Plugins'
    want_schedule = input("Need schedule polling mode? [y/N]: ").strip().lower() == 'y'

    print("\n--- Input fields (key:type:label, blank line to finish; types string/int/bool) ---")
    inputs = []
    while True:
        line = input("  input> ").strip()
        if not line:
            break
        parts = line.split(':', 2)
        if len(parts) != 3:
            print("  format: key:type:label"); continue
        inputs.append({'key': parts[0], 'type': parts[1], 'label': parts[2]})

    print("\n--- Output fields (same format) ---")
    outputs = []
    while True:
        line = input("  output> ").strip()
        if not line:
            break
        parts = line.split(':', 2)
        if len(parts) != 3:
            print("  format: key:type:label"); continue
        outputs.append({'key': parts[0], 'type': parts[1], 'label': parts[2]})

    outdir = input("\nOutput root dir (SOPS code/ root, e.g. /data/app/code): ").strip()
    static_root = input("STATIC_ROOT dir for JS forms (e.g. /data/app/code/bk_sops/static, blank to skip): ").strip()
    return {
        'code': code, 'name': name, 'system': system, 'system_label': system_label,
        'schedule': want_schedule, 'inputs': inputs, 'outputs': outputs,
        'outdir': outdir or '.', 'static_root': static_root or None,
    }


def _build_py(ctx):
    py_inputs = '\n'.join(_py_input(i['key'], i['label'], i['type']) for i in ctx['inputs'])
    py_outputs = '\n'.join(_py_output(o['key'], o['label'], o['type']) for o in ctx['outputs'])
    schedule_import = SCHEDULE_IMPORT if ctx['schedule'] else ''
    schedule_block = SCHEDULE_BLOCK if ctx['schedule'] else ''
    return PY_TEMPLATE.format(
        code=ctx['code'], name=ctx['name'], system=ctx['system'],
        system_label=ctx['system_label'],
        service_class=_class_name(ctx['code']) + 'Service',
        component_class=_class_name(ctx['code']) + 'Component',
        inputs_block=py_inputs or '            # TODO: declare input fields',
        outputs_block=py_outputs or '            # TODO: declare output fields',
        schedule_gen=schedule_import,
        schedule_block=schedule_block,
    )


def _build_js(ctx):
    fields = '\n'.join(_js_field(i['key'], i['label'], i['type']) for i in ctx['inputs'])
    return JS_TEMPLATE.format(code=ctx['code'], fields_block=fields or '        // TODO: configure form fields')


def main():
    ap = argparse.ArgumentParser(description='SOPS PluginNode scaffold')
    ap.add_argument('--code', help='Unique plugin code (e.g. my_http)')
    ap.add_argument('--name', help='Display name (e.g. HTTP Health Check)')
    ap.add_argument('--system', default='custom', help='System group directory')
    ap.add_argument('--system-label', default='Custom Plugins', help='Group display label')
    ap.add_argument('--schedule', action='store_true', help='Include schedule() polling skeleton')
    ap.add_argument('--input', action='append', default=[], metavar='KEY:TYPE:LABEL',
                    help='Input field (string/int/bool), repeatable')
    ap.add_argument('--output', action='append', default=[], metavar='KEY:TYPE:LABEL',
                    help='Output field, repeatable')
    ap.add_argument('--outdir', default='.', help='Output root (SOPS code/ directory)')
    ap.add_argument('--static-root', default=None,
                    help='Optional Django STATIC_ROOT (e.g. code/static); '
                         'if given, JS form is also copied there')
    args = ap.parse_args()

    if not args.code:
        ctx = _interactive()
    else:
        ctx = {
            'code': args.code, 'name': args.name or args.code,
            'system': args.system, 'system_label': args.system_label,
            'schedule': args.schedule,
            'inputs': [dict(zip(('key', 'type', 'label'), v.split(':', 2))) for v in args.input],
            'outputs': [dict(zip(('key', 'type', 'label'), v.split(':', 2))) for v in args.output],
            'outdir': args.outdir, 'static_root': args.static_root,
        }

    py_dir = os.path.join(ctx['outdir'], 'pipeline_plugins', 'components', 'collections', ctx['system'])
    js_dir = os.path.join(ctx['outdir'], 'pipeline_plugins', 'components', 'static',
                          'components', 'atoms', ctx['system'])
    py_path = os.path.join(py_dir, 'v1_0.py')
    js_path = os.path.join(js_dir, ctx['code'] + '.js')

    os.makedirs(py_dir, exist_ok=True)
    os.makedirs(js_dir, exist_ok=True)

    # New system subdirs need __init__.py for pkgutil.iter_modules to find them
    py_init = os.path.join(py_dir, '__init__.py')
    if not os.path.exists(py_init):
        open(py_init, 'w', encoding='utf-8').write('# generated by sopps-plugin-scaffold\n')

    with open(py_path, 'w', encoding='utf-8') as f:
        f.write(_build_py(ctx))
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(_build_js(ctx))

    # JS form must also land in Django STATIC_ROOT for the browser to serve it
    static_root = args.static_root or ctx.get('static_root')
    if static_root:
        static_js_dir = os.path.join(static_root, 'components', 'atoms', ctx['system'])
        os.makedirs(static_js_dir, exist_ok=True)
        static_js_path = os.path.join(static_js_dir, ctx['code'] + '.js')
        with open(static_js_path, 'w', encoding='utf-8') as f:
            f.write(_build_js(ctx))

    print("\n✓ Scaffold generated:")
    print("  Backend :", py_path)
    print("  JS src  :", js_path)
    if static_root:
        print("  JS static:", static_js_path)
    print("\nNext: build a new image with these files (Dockerfile.plugins, see "
          "SOPS_PLUGIN_SCAFFOLD.md), then redeploy the container.")


if __name__ == '__main__':
    main()
