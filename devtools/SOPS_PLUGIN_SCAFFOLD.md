# SOPS PluginNode Scaffold

A single-file CLI that generates a new SOPS custom plugin skeleton — Python backend + JS frontend form — in one shot.

## Quick Start

```bash
# 1. Generate the plugin skeleton into a local staging dir
python3 sopps-plugin-scaffold.py \
  --code http_health_check \
  --name "HTTP Health Check" \
  --system http \
  --outdir ./sops-plugins/code \
  --static-root ./sops-plugins/static \
  --input url:string:"Target URL" \
  --input timeout:int:"Timeout sec (default 10)" \
  --output status_code:int:"HTTP Status" \
  --output ok:bool:"Passed"

# 2. Build a new SOPS image with the plugin baked in
docker build -t bkce-sops:plugins -f Dockerfile.plugins ./sops-plugins

# 3. Deploy: point your compose/service at the new tag and recreate the container
#    (e.g. update `image:` in docker-compose.yml, then)
docker compose up -d bkce-sops
```

Plugins live in the image — never `docker cp` files into a running container. That keeps deployments reproducible and survives container recreation.

## Usage Modes

### Interactive (Q&A)

```bash
python3 sopps-plugin-scaffold.py
```

Prompts for code, name, system group, inputs/outputs, output directory, and static root.

### CLI Arguments

| Flag | Required | Description |
|------|----------|-------------|
| `--code` | Yes (or interactive) | Unique plugin identifier, lowercase + underscore, e.g. `http_health_check`. Also becomes the DB primary key. |
| `--name` | No | Display name shown on canvas. Defaults to `--code`. |
| `--system` | No | System group directory under `collections/` and `atoms/`, e.g. `http`, `job`, `custom`. Default `custom`. |
| `--system-label` | No | Group label shown on canvas under the plugin name. Default `Custom Plugins`. |
| `--schedule` | No | Include `schedule()` polling skeleton. Use when the node needs async/callback execution. |
| `--input KEY:TYPE:LABEL` | Repeatable | Declare an input field. `TYPE` ∈ `string` / `int` / `bool`. |
| `--output KEY:TYPE:LABEL` | Repeatable | Declare an output field (accessible to downstream nodes via `${node_code.output_key}`). |
| `--outdir` | No | Local staging root for the **Python + JS source files**. Default `.`. This directory mirrors the container's `/data/app/code` layout and is what the Dockerfile COPYs. |
| `--static-root` | No | Local staging root for the **JS form copy** (mirrors the container's `bk_sops/static`). If omitted, only source files are generated — the image build then only needs one COPY. |

## File Layout

SOPS separates **auto-discovery** from **static file serving**. The scaffold generates a local staging tree that mirrors the container paths, so the Dockerfile is a plain directory COPY:

```
# Local staging (what you commit / what the Dockerfile COPYs)
{OUTDIR}/pipeline_plugins/components/collections/<system>/
├── __init__.py            # auto-created for new system dirs (pkgutil needs it)
└── v1_0.py                # Python backend — auto-discovered at startup

{OUTDIR}/pipeline_plugins/components/static/components/atoms/<system>/
└── <code>.js              # JS form source (human-editable)

{STATIC_ROOT}/components/atoms/<system>/
└── <code>.js              # JS form copy (browser loads from here)

# Container mapping (what the Dockerfile mounts where)
{OUTDIR}/pipeline_plugins/...   →  /data/app/code/pipeline_plugins/...
{STATIC_ROOT}/...               →  /data/app/code/bk_sops/static/...
```

**Why two JS copies?** SOPS's uwsgi config has `static-map = /o/bk_sops/static=/data/app/code/bk_sops/static`. Django `staticfiles` is not enabled, so only files under `bk_sops/static/` are web-accessible. The `pipeline_plugins/.../static/` copy is the canonical source; both scaffold and upstream plugins ship it this way.

## Build & Deploy a New Image

Generate → build → deploy. Replace the base image tag with your current one.

**Step 1 — generate into the staging dir** (see Quick Start).

**Step 2 — `Dockerfile.plugins`** (next to the staging dir):

```dockerfile
FROM crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops/bkce-sops:v6

# Python backend + JS source — auto-discovered on container start
COPY --chown=apps:apps code/pipeline_plugins/ /data/app/code/pipeline_plugins/

# JS forms — served by uwsgi static-map
COPY --chown=apps:apps static/ /data/app/code/bk_sops/static/
```

Build with the staging dir as context:

```bash
docker build -t bkce-sops:plugins -f Dockerfile.plugins ./sops-plugins
```

**Step 3 — deploy the new container.** Update the `image:` for `bkce-sops` in your `docker-compose.yml` (or your orchestrator of choice), then:

```bash
docker compose up -d bkce-sops
```

On container start, `ComponentFrameworkConfig.ready()` auto-discovers the plugin and registers it in `bk_sops.component_framework_componentmodel` — no manual uwsgi restart needed for image-baked plugins.

To push the result to a registry:

```bash
docker tag bkce-sops:plugins crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops/bkce-sops:v7
docker push crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops/bkce-sops:v7
```

## Fill in the Logic

The scaffold generates a `Service` class with an `execute()` skeleton. Add your business logic there:

```python
def execute(self, data, parent_data):
    # --- Read inputs ---
    url     = data.get_one_of_inputs('url') or ''
    timeout = int(data.get_one_of_inputs('timeout') or 10)

    # --- Your logic ---
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        status = resp.getcode()
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        status = 0

    # --- Write outputs (accessible as ${node_code.status}) ---
    data.outputs.status = status
    data.outputs.ok     = (status == 200)

    # Return True = node succeeded (outputs are valid)
    # Return False = retryable failure
    # raise Exception = hard failure
    return True
```

### Lifecycle Reference

| Method | When | Typical Use |
|--------|------|-------------|
| `execute(data, parent_data)` | Node starts | Synchronous work, single-shot execution |
| `schedule(data, parent_data, callback_data)` | Called repeatedly | Async polling; call `self.finish_schedule()` when done, `self.schedule_fail()` on failure |

### Data Objects

| Object | How to |
|--------|--------|
| Read input | `data.get_one_of_inputs('field_key')` |
| Write output | `data.outputs.field_key = value` |
| Read global vars | `parent_data.inputs['global_key']` |
| Output in downstream node | `${previous_node_code.field_key}` |

## Schema Type Mapping

| Input/Output type | Python Schema class | JS form widget |
|-------------------|---------------------|----------------|
| `string` | `StringItemSchema` | `input` |
| `int` | `IntItemSchema` | `int` |
| `bool` | `BooleanItemSchema` | `checkbox` |

## Examples

### 1. Simple Command Runner (no schedule)

```bash
python3 sopps-plugin-scaffold.py \
  --code run_command \
  --name "Run Shell Command" \
  --system job \
  --input command:string:"Command" \
  --input timeout:int:"Timeout sec" \
  --output exit_code:int:"Exit Code" \
  --output stdout:string:"Stdout (first 500 chars)" \
  --output ok:bool:"Passed" \
  --outdir ./sops-plugins/code \
  --static-root ./sops-plugins/static
```

### 2. Async Deployment Check (with schedule)

```bash
python3 sopps-plugin-scaffold.py \
  --code poll_deploy \
  --name "Poll Deployment" \
  --system custom \
  --schedule \
  --input deploy_id:string:"Deployment ID" \
  --output status:string:"Current Status" \
  --output ok:bool:"Succeeded" \
  --outdir ./sops-plugins/code \
  --static-root ./sops-plugins/static
```

Then in `schedule()`:

```python
def schedule(self, data, parent_data, callback_data=None):
    deploy_id = data.get_one_of_inputs('deploy_id')
    status = _query_deploy_status(deploy_id)
    data.outputs.status = status
    if status == 'SUCCEEDED':
        data.outputs.ok = True
        self.finish_schedule()
    elif status in ('FAILED', 'TIMEOUT'):
        data.outputs.ok = False
        self.schedule_fail()
    # else keep polling
```

## Pitfalls

- **Forgot `--static-root`**: Plugin imports fine, DB record exists, but the browser shows a blank form or 404 — because the JS isn't in `bk_sops/static/`.
- **New system dir without `__init__.py`**: The scaffold auto-creates it. If you manually add a new system dir, `pkgutil.iter_modules` won't descend into it without `__init__.py`.
- **`BoolItemSchema` does not exist**: The real class is `BooleanItemSchema`. The scaffold template uses the correct one.
- **Plugin not visible after deploy**: Check that `ComponentFrameworkConfig.ready()` ran (uwsgi startup logs). If the Python file has a syntax or import error, autodiscovery logs it but continues — check uwsgi logs for `import failed`.
- **Stale container after rebuild**: If you rebuild the image with the same tag, `docker compose up -d` may not recreate the container. Use a new tag per build, or force with `docker compose up -d --force-recreate bkce-sops`.
- **Don't `docker cp` into running containers**: Changes vanish on container recreation and drift from the image. Always bake plugins into the image via the Dockerfile. (`docker exec` for read-only debugging is fine.)

## Verification Commands

After deploying the new image:

```bash
# DB registration check (auto-registered on container start)
docker exec bkce-data mysql -h127.0.0.1 -P3306 -upaas -pZhqXgXfwUfVS \
  -D bk_sops -e "SELECT code, name, version, status FROM component_framework_componentmodel;"
# status=1 means activated

# JS form reachable
curl -s -o /dev/null -w '%{http_code}\n' \
  "http://localhost:8080/o/bk_sops/static/components/atoms/custom/my_plugin.js"
# expect 200

# Import check inside the container
docker exec bkce-sops python /data/app/code/manage.py shell -c \
  "from pipeline_plugins.components.collections.custom.v1_0 import MyComponent; print(MyComponent.code)"
```

Then hard-refresh the SOPS canvas in your browser (JS forms are cached) — the plugin appears under its group in the left panel.
