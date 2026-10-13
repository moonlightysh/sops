# bkce-sops — Standard OPS SaaS (lightweight standalone stack)
#
# Build equation:  image = community source (src/, untouched) + our patches
#                  (patches/bkce-sops/) on top of the runtime base
#                  (python venv / system deps from bkce-sops:v6).
#
# src/ = TencentBlueKing/bk-sops tag V3.25.12, verbatim — the release the
#        deployed containers were built from (STATIC_VERSION 3.25.12).
#        Upgrading community code = replace src/ with the new tag, then
#        rebase patches/ onto it; the two trees never mix.
#
#   bash build/merge.sh   ← 预览：融合 src/ + patches/ 到 /tmp/sops_merged + 写 stamp
#   bash build/build.sh   ← 生产：校验 stamp → 构建完整镜像（注入 venv/系统依赖）
#
# NOTE: the merge steps in merge.sh mirror the pure_merge stage below
# (COPY src/ → COPY patches/); keep the two in sync.

# Global ARG (before the first FROM) so the runtime FROM can use it and
# `docker build --target pure_merge` still parses this file without overrides.
ARG BASE_IMAGE=moonlightysh/bkce-sops:v6

# ---------------------------------------------------------------------------
# Stage 1: PURE_MERGE — src/ + patches/ layered, NO runtime deps.
#           build/merge.sh reproduces exactly this layering locally.
# ---------------------------------------------------------------------------
FROM scratch AS pure_merge
COPY src/ /code/
COPY patches/bkce-sops/code/ /code/
COPY patches/bkce-sops/conf/ /conf/

# ---------------------------------------------------------------------------
# Stage 2: RUNTIME — full image with python venv / system deps on top.
#           build.sh: --target runtime --build-arg BASE_IMAGE=<registry>/bkce-sops:<tag>
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS runtime

COPY --from=pure_merge /code/ /data/app/code/
COPY --from=pure_merge /conf/ /data/app/conf/

RUN chown -R apps:apps /data/app/code && \
    rm -f /data/app/code/gcloud/core/utils/sites/open/utils.py.orig.bak
