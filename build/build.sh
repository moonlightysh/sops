#!/usr/bin/env bash
#
# Build bkce-* images reproducibly:
#   ACR base images + src/ (community bk-sops V3.25.12) + patches/ overlay.
#
# Usage:
#   ./build/build.sh                     # build standalone images (data + sops)
#   ./build/build.sh sops data           # build selected components
#   TAG=v8 ./build/build.sh              # tag as v8 (overwrites local v8 tag)
#   PUSH=1 TAG=v8 ./build/build.sh       # build + push to ACR
#
# NOTE: build context must be the repository root (Dockerfiles COPY patches/).

set -euo pipefail

REG="${REG:-crpi-0oxtvczw7n94n0bz.cn-hangzhou.personal.cr.aliyuncs.com/sops}"
TAG="${TAG:-v8-build}"
BASE_TAG="${BASE_TAG:-v3}"             # legacy base tags (unused by data/sops below)
BASE_TAG_DATA="${BASE_TAG_DATA:-v2}"   # bkce-data has no v3 on ACR (v2 -> v4)
BASE_TAG_SOPS="${BASE_TAG_SOPS:-v6}"   # standalone sops base (2-container stack)
cd "$(dirname "$0")/.."   # repo root

COMPONENTS="${*:-data sops}"

for c in $COMPONENTS; do
  if [ ! -f "build/$c/Dockerfile" ]; then
    echo "skip: build/$c/Dockerfile not found" >&2
    continue
  fi
  base="$BASE_TAG"; [ "$c" = "data" ] && base="$BASE_TAG_DATA"; [ "$c" = "sops" ] && base="$BASE_TAG_SOPS"
  echo "==> building bkce-$c:$TAG (base bkce-$c:$base)"
  docker build -f "build/$c/Dockerfile" \
    --build-arg REGISTRY="$REG" --build-arg BASE_TAG="$base" \
    --provenance=false --sbom=false \
    -t "$REG/bkce-$c:$TAG" .
  if [ "${PUSH:-0}" = "1" ]; then
    docker push "$REG/bkce-$c:$TAG"
  fi
done
echo "==> done: $COMPONENTS tagged $TAG"
