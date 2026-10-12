# bksops-lite

Standalone 2-container BlueKing **Standard OPS** (bk-sops) for local macOS
(Docker Desktop): patch overlay + reproducible build tooling, no full source
tree. See [PATCHES.md](PATCHES.md) for what is modified and why.

## Architecture

    host :8080 ──▶ bkce-sops  (uwsgi http :8010, OIDC RP + standalone auth)
                      │  consul DNS (*.service.consul) / fixed IPs 172.18.107.0/24
                      ▼
                  bkce-data  (mysql / redis / rabbitmq / consul, IP 172.18.107.16)

- `bkce-data` also hosts **consul** (moved out of the retired paas container):
  DNS on :53 resolves `mysql-default.service.consul`, `rabbitmq.service.consul`, etc.
- Auth is fully standalone: OIDC login against a mock company IAM
  (`devtools/mock_iam.py`, RS256), `bk_token` verified in-process
  (AES-128-ECB), no paas/login/usermgr containers.

## Quickstart

    docker compose up -d          # bkce-data + bkce-sops (images from ACR, sops ns)
    python3 devtools/mock_iam.py  # mock IdP on 0.0.0.0:5556 (run in background)
    open http://localhost:8080    # redirects to /o/bk_sops/ → mock IAM login

Test users: `alice/alice123` (SOPS-ADMIN), `bob/bob123` (PM + VIEWER).

## Build images from this repo

    ./build/build.sh                # data + sops, tags bkce-*:v7-build
    PUSH=1 TAG=v7 ./build/build.sh  # build + push to ACR

Note: `build/data/consul` (gitignored) must exist — regenerate with
`docker cp bkce-data:/usr/bin/consul build/data/consul` if missing.

## Plugin development

See [devtools/SOPS_PLUGIN_SCAFFOLD.md](devtools/SOPS_PLUGIN_SCAFFOLD.md).
Workflow: scaffold generates plugin files into a local staging dir → the files
are added under `patches/bkce-sops/code/...` → `docker build` a new image →
deploy the updated container. Running containers are never modified in place.

## Verification

    python3 devtools/test_mock_iam.py   # unit tests (stdlib unittest)
    bash devtools/e2e_login_test.sh     # full login chain: / → OIDC → Standard OPS 200
