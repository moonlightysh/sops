#!/usr/bin/env bash
#
# Merge src/ + patches/ into a reviewable local tree BEFORE any runtime image
# is built, and write a stamp that build.sh checks as a precondition.
#
# The merge steps below mirror build/sops/Dockerfile's pure_merge stage
# (COPY src/ → COPY patches/) — keep the two in sync.  This script runs the
# merge locally (fast, no venv needed) and writes a stamp; build.sh validates
# the stamp, then builds the runtime image through docker.
#
# Usage:
#   bash build/merge.sh               # default: /tmp/sops_merged
#   TARGET=/somewhere/else bash build/merge.sh
#   bash build/merge.sh --diff        # inventory of our changes vs upstream
#
# Outputs live under /tmp — never commit them.

set -e
cd "$(dirname "$0")/.."   # repo root

TARGET="${TARGET:-/tmp/sops_merged}"
STAMP_FILE="/tmp/sops_merge.stamp"

# Compute a content hash over EVERY input that affects the merge result.
# Any change to src/ or patches/ changes this hash → build.sh will reject it.
compute_hash() {
  find src patches -type f \
      | sort \
      | xargs shasum \
      | shasum \
      | cut -d' ' -f1
}

if [ "${1:-}" = "--diff" ]; then
  echo "=== our changes vs upstream (src/) ==="
  MODIFIED=0
  NEW=0
  while IFS= read -r patch_file; do
    rel="${patch_file#patches/bkce-sops/code/}"
    if [ -f "src/$rel" ]; then
      if ! cmp -s "src/$rel" "$patch_file"; then
        echo "MODIFY : $rel"
        MODIFIED=$((MODIFIED + 1))
      fi
    else
      echo "ADD    : $rel"
      NEW=$((NEW + 1))
    fi
  done < <(find patches/bkce-sops/code -type f)
  echo
  echo "modified=$MODIFIED  new=$NEW  total=$((MODIFIED + NEW))"
  exit 0
fi

echo "==> merging src/ + patches/bkce-sops/{code,conf}/ -> $TARGET"
rm -rf "$TARGET"

# 1. community source, verbatim
mkdir -p "$TARGET/code"
cp -R src/. "$TARGET/code/"

# 2. patches overlay (same-path files overwritten, new files added)
cp -R patches/bkce-sops/code/. "$TARGET/code/"

# 3. confs live in /data/app/conf/ (not /data/app/code/)
mkdir -p "$TARGET/conf"
cp -R patches/bkce-sops/conf/. "$TARGET/conf/"

# drop patch backup files
find "$TARGET" \( -name '*.orig' -o -name '*.orig.bak' \) -exec rm -f {} \;

# write stamp so build.sh knows merge has happened on the current inputs
HASH=$(compute_hash)
echo "hash=$HASH"     > "$STAMP_FILE"
echo "time=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STAMP_FILE"

echo
echo "    merged -> $TARGET"
echo "    stamp  -> $STAMP_FILE  (hash=$HASH)"
echo "  review tips:"
echo "    diff src/ $TARGET/code/                              # ALL changes"
echo "    diff src/wsgi.py patches/bkce-sops/code/wsgi.py       # single patch"
echo "    bash build/merge.sh --diff                            # patch inventory"
echo
echo "  next:  bash build/build.sh    (build.sh validates the stamp)"
