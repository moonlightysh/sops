# Patch Manifest

This repository is the **patch overlay + build tooling** for the 2-container
standalone BlueKing Standard OPS stack (`bkce-data` + `bkce-sops`). It does NOT
contain the full BlueKing source tree (upstream: <https://github.com/TencentBlueKing>,
MIT). It holds the **modified files**, extracted from the container images and
organized by container, with the pristine upstream file kept as `*.orig` where
available. Apply them on top of the corresponding upstream files, or use the
published images (ACR namespace `sops`) built by `build/build.sh`.

## bkce-sops (Standard OPS)

| File | Change |
|------|--------|
| `code/wsgi.py` (+`.orig`) | Three WSGI-layer patches: (1) static-file middleware — serves `/o/bk_sops/static/` and `/static/` from `bk_sops/static` (uwsgi `static-map` is incompatible with `mount` + `manage-script-name`); (2) OIDC RP at `/o/bk_sops/login/oauth/{login,callback}/` — RS256 JWKS verification with stdlib only, maps IAM groups to SOPS roles, seeds users into `open_paas.account_bkuser` + `bk_user_manage.account_bkuser` + `open_paas.login_bktoken`; (3) standalone auth — blueapps `TokenBackend` monkey-patched: `verify_bk_token` = in-process AES-128-ECB decrypt (no login service needed), `get_user_info` reads the seeded rows; 401 login redirects point at the OIDC entry. Plus `/` → `/o/bk_sops/` root redirect |
| `code/config/default.py` | `LANGUAGE_CODE = "en"` — backend default language English |
| `code/gcloud/core/apis/drf/serilaziers/component_model.py` | `to_representation` pads the `"<group>-<name>"` split when fewer than 2 parts — malformed component names no longer 500 the whole `/api/v3/component/` list |
| `code/pipeline_plugins/components/collections/custom/` | Scaffold-generated custom plugin backend (`v1_0.py` = HTTP health check), baked into the image |
| `code/bk_sops/static/components/atoms/custom/my_http_check.js` | Frontend atom for the custom plugin |
| `conf/bk_sops.ini` | uwsgi `http = 0.0.0.0:8010` added (upstream binds unix socket only); compose maps host `8080` → `8010` |
| `conf/supervisord.conf` | uwsgi program environment: `BK_IAM_SKIP="true"` (DummyIAM allow-all — no IAM policy engine in this stack) + `BK_OIDC_ISSUER/SERVER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI` for the OIDC login |

## bkce-data (MySQL / Redis / RabbitMQ / Consul)

| File | Change |
|------|--------|
| `entrypoint.sh` | consul starts **FIRST** (moved here from the removed paas container — SaaS containers resolve `*.service.consul` via its DNS), then mysqld (daemonize) + rabbitmq (longname node; hostname fixed via compose `hostname:`) |
| `watchdog/consul_watchdog.sh` | 5s poll; respawns consul after Docker Desktop OOM kills |
| `watchdog/mysql_watchdog.sh` | 5s poll; respawns mysqld — without it SaaS containers crash-loop on migrate at first boot |
| `watchdog/redis_watchdog.sh` | Health-based ping (`NOAUTH` counts as alive — redis has `requirepass`); 5s poll |
| `consul/consul.json`, `consul/server.json` | DNS :53 + HTTP :8500 on 0.0.0.0, single server (`bootstrap_expect 1`) |
| `consul/service/*.json` | Declarative service defs registering `mysql-default` / `rabbitmq` / `redis` with TCP health checks on 172.18.107.16 |

## Build

`build/build.sh` builds `bkce-data` (base `v2`) and `bkce-sops` (base `v6`)
from this repo. `build/data/consul` (gitignored) is the consul binary extracted
from the retired paas image; regenerate if missing:

    docker cp bkce-data:/usr/bin/consul build/data/consul

## Legacy components

`bkce-paas` / `bkce-iam` / `bkce-usermgr` images remain on ACR for the retired
5-container stack, but their patch trees are **not** carried in this repository.

## Security notes

- IAM is **allow-all** in this stack (SOPS `BK_IAM_SKIP` DummyIAM). Fine for
  isolated lab deployments; harden before any shared use.
- The mock IdP (`devtools/mock_iam.py`) accepts fixed test credentials
  (alice/alice123, bob/bob123). Never expose it beyond localhost.
- Default SOPS credentials: `admin / Blueking@2019` — rotate immediately.
