#!/usr/bin/env bash
#
# Merge src/ + patches/ into a single preview tree for review BEFORE building
# any container. Mirrors exactly what build/sops/Dockerfile does inside the
# image:
#
#   /data/app/code/  = src/  +  patches/bkce-sops/code/  (overlay)
#   /data/app/conf/  =            patches/bkce-sops/conf/
#
# Usage:
#   bash build/merge.sh               # default: /tmp/sops_merged
#   TARGET=/somewhere/else bash build/merge.sh
#   bash build/merge.sh --diff        # inventory of our changes vs upstream
#
# Output is gitignored — never commit merged/.

set -e
cd "$(dirname "$0")/.."   # repo root

TARGET="${TARGET:-/tmp/sops_merged}"

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

echo
echo "    merged -> $TARGET"
echo "  review tips:"
echo "    diff src/ $TARGET/code/                              # ALL changes"
echo "    diff src/wsgi.py patches/bkce-sops/code/wsgi.py       # single patch"
echo "    bash build/merge.sh --diff                            # patch inventory"
