# bksops-lite

Standalone 2-container BlueKing **Standard OPS** (bk-sops) for local macOS
(Docker Desktop): pristine community source (`src/`, bk-sops **V3.25.12**) +
our patch overlay (`patches/`) + reproducible build tooling. Community code
and our changes live in separate directories, so upstream upgrades stay clean
and reviewable. See [PATCHES.md](PATCHES.md) for what is modified and why.

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

    ./build/build.sh                # data + sops, tags bkce-*:v8-build
    PUSH=1 TAG=v8 ./build/build.sh  # build + push to ACR

The `bkce-sops` image is assembled layer by layer:

    runtime base bkce-sops:v6   (venv / system deps, from ACR)
    + COPY src/                          → /data/app/code/   # community V3.25.12, untouched
    + COPY patches/bkce-sops/code/       → overlaid on top   # our changes
    + COPY patches/bkce-sops/conf/       → overlaid on top

`src/` is the pristine upstream tree (`git archive` of tag `V3.25.12`) and is
never edited directly — every change goes into `patches/`.

Note: `build/data/consul` (gitignored) must exist — regenerate with
`docker cp bkce-data:/usr/bin/consul build/data/consul` if missing.

### Upgrading the community source

Replace `src/` with the newer bk-sops release tree (e.g.
`git archive <newer-tag> | tar -x -C src/`), then re-check every file under
`patches/bkce-sops/code/` against the new tree — a patch whose upstream
counterpart changed needs re-basing. Nothing else in the build changes.

## Plugin development

See [devtools/SOPS_PLUGIN_SCAFFOLD.md](devtools/SOPS_PLUGIN_SCAFFOLD.md).
Workflow: scaffold generates plugin files into a local staging dir → the files
are added under `patches/bkce-sops/code/...` → `docker build` a new image →
deploy the updated container. Running containers are never modified in place.

## Verification

    python3 devtools/test_mock_iam.py   # unit tests (stdlib unittest)
    bash devtools/e2e_login_test.sh     # full login chain: / → OIDC → Standard OPS 200
