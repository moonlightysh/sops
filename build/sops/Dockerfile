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
ARG REGISTRY=crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops
ARG BASE_TAG=v6
FROM ${REGISTRY}/bkce-sops:${BASE_TAG}

# community source, verbatim
COPY src/ /data/app/code/

# our patches overlay the same paths (only modified/added files live here)
COPY patches/bkce-sops/code/ /data/app/code/

# uwsgi + supervisord confs
COPY patches/bkce-sops/conf/ /data/app/conf/

# code files are owned by apps in the base image; drop stale patch backups
RUN chown -R apps:apps /data/app/code && \
    rm -f /data/app/code/gcloud/core/utils/sites/open/utils.py.orig.bak
