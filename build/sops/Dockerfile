# bkce-sops — Standard OPS SaaS, standalone entry (2-container stack: data + sops)
#
# Base: bkce-sops:v6 (standalone: uwsgi http :8010, no paas dependency).
# This layer adds the v7 patches: OIDC login WSGI, component_model fallback
# and the scaffold-generated custom plugin (backend collection + frontend atom).
ARG REGISTRY=crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops
ARG BASE_TAG=v6
FROM ${REGISTRY}/bkce-sops:${BASE_TAG}

# WSGI entry: OIDC RP (/o/bk_sops/login/oauth/*) + in-process bk_token auth + / root redirect
COPY patches/bkce-sops/code/wsgi.py /data/app/code/wsgi.py

# site config: LANGUAGE_CODE=en
COPY patches/bkce-sops/code/config/default.py /data/app/code/config/default.py

# component serializer: canvas group/name split fallback (malformed names no longer 500)
COPY patches/bkce-sops/code/gcloud/core/apis/drf/serilaziers/component_model.py \
     /data/app/code/gcloud/core/apis/drf/serilaziers/component_model.py

# scaffold-generated custom plugin: backend collection + frontend atom JS
COPY patches/bkce-sops/code/pipeline_plugins/components/collections/custom/ \
     /data/app/code/pipeline_plugins/components/collections/custom/
COPY patches/bkce-sops/code/bk_sops/static/components/atoms/custom/ \
     /data/app/code/bk_sops/static/components/atoms/custom/

# uwsgi http bind (:8010) + supervisord env (BK_IAM_SKIP etc.)
COPY patches/bkce-sops/conf/bk_sops.ini /data/app/conf/bk_sops.ini
COPY patches/bkce-sops/conf/supervisord.conf /data/app/conf/supervisord.conf

# code files are owned by apps in the base image
RUN chown apps:apps /data/app/code/wsgi.py \
                    /data/app/code/config/default.py \
                    /data/app/code/gcloud/core/apis/drf/serilaziers/component_model.py && \
    chown -R apps:apps /data/app/code/pipeline_plugins/components/collections/custom \
                       /data/app/code/bk_sops/static/components/atoms/custom
