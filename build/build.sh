#!/usr/bin/env bash
#
# Build bkce-* images reproducibly:
#   ACR base images + src/ (community bk-sops V3.25.12) + patches/ overlay.
#
# PRECONDITION:  bash build/merge.sh must have been run AFTER the last change
#                to src/ or patches/ — the stamp /tmp/sops_merge.stamp is
#                validated below.  Use FORCE=1 to skip the check.
#
# Usage:
#   bash build/merge.sh                     # review + write stamp (required)
#   FORCE=1 bash build/build.sh             # skip merge pre-check
#   bash build/build.sh                     # build images (data + sops)
#   TAG=v9 PUSH=1 bash build/build.sh       # tag + push to Docker Hub

set -euo pipefail

REG="${REG:-moonlightysh}"
TAG="${TAG:-v8-build}"
BASE_TAG="${BASE_TAG:-v3}"             # legacy base tags (unused by data/sops below)
BASE_TAG_DATA="${BASE_TAG_DATA:-v2}"   # bkce-data has no v3 on ACR (v2 -> v4)
BASE_TAG_SOPS="${BASE_TAG_SOPS:-v6}"   # standalone sops base (2-container stack)
cd "$(dirname "$0")/.."   # repo root

STAMP_FILE="/tmp/sops_merge.stamp"

# --- pre-check: merge.sh must have run on current inputs ---
if [ "${FORCE:-0}" != "1" ]; then
  if [ ! -f "$STAMP_FILE" ]; then
    echo "ERROR: merge stamp not found at $STAMP_FILE" >&2
    echo "       Run: bash build/merge.sh" >&2
    echo "       (skip this check with FORCE=1 if you know what you're doing)" >&2
    exit 1
  fi

  # compute current inputs hash, compare with stamp
  CURR_HASH=$(find src patches -type f \
                 | sort \
                 | xargs shasum \
                 | shasum \
                 | cut -d' ' -f1)
  STAMP_HASH=$(grep '^hash=' "$STAMP_FILE" | cut -d= -f2)

  if [ "$CURR_HASH" != "$STAMP_HASH" ]; then
    echo "ERROR: src/ or patches/ changed since last merge.sh" >&2
    echo "       stamp hash : $STAMP_HASH" >&2
    echo "       current    : $CURR_HASH" >&2
    echo "       Re-run: bash build/merge.sh" >&2
    echo "       (skip with FORCE=1 if you know what you're doing)" >&2
    exit 1
  fi

  echo "==> merge stamp OK (hash=$CURR_HASH)"
fi

COMPONENTS="${*:-data sops}"

for c in $COMPONENTS; do
  if [ ! -f "build/$c/Dockerfile" ]; then
    echo "skip: build/$c/Dockerfile not found" >&2
    continue
  fi
  base="$BASE_TAG"; [ "$c" = "data" ] && base="$BASE_TAG_DATA"; [ "$c" = "sops" ] && base="$BASE_TAG_SOPS"
  echo "==> building bkce-$c:$TAG (base bkce-$c:$base)"
  if [ "$c" = "sops" ]; then
    # sops Dockerfile is multi-stage: pure_merge (src+patches) → runtime
    # (--target runtime; base image via BASE_IMAGE build-arg)
    docker build -f "build/$c/Dockerfile" \
      --target runtime \
      --build-arg BASE_IMAGE="${REG}/bkce-$c:$base" \
      --provenance=false --sbom=false \
      -t "$REG/bkce-$c:$TAG" .
  else
    docker build -f "build/$c/Dockerfile" \
      --build-arg REGISTRY="$REG" --build-arg BASE_TAG="$base" \
      --provenance=false --sbom=false \
      -t "$REG/bkce-$c:$TAG" .
  fi
  if [ "${PUSH:-0}" = "1" ]; then
    docker push "$REG/bkce-$c:$TAG"
  fi
done
echo "==> done: $COMPONENTS tagged $TAG"
