#!/usr/bin/env bash
# E2E login chain for the standalone stack:
#   / -> /o/bk_sops/ -> OIDC login (mock IAM, alice) -> callback -> 200 "Standard OPS"
# Requires: docker compose stack up + devtools/mock_iam.py running on :5556.
set -u
B=http://localhost:8080
J=$(mktemp); H=$(mktemp)
fail() { echo "FAIL: $1"; exit 1; }

echo "== 1. / -> 302 /o/bk_sops/"
r=$(curl -s -o /dev/null -w "%{http_code}|%{redirect_url}" $B/)
echo "   $r"
case "$r" in 302*"/o/bk_sops/"*) ;; *) fail "step1";; esac

echo "== 2. /o/bk_sops/ -> 302 OIDC login"
r=$(curl -s -c "$J" -o /dev/null -w "%{http_code}|%{redirect_url}" $B/o/bk_sops/)
echo "   $r"
case "$r" in 302*login/oauth/login*) ;; *) fail "step2";; esac
LOGIN_URL="${r#*|}"

echo "== 3. login RP -> 302 mock IAM /authorize"
r=$(curl -s -b "$J" -c "$J" -o /dev/null -w "%{http_code}|%{redirect_url}" "$LOGIN_URL")
echo "   $r"
case "$r" in 302*"/authorize"*) ;; *) fail "step3";; esac
AUTH_URL="${r#*|}"

echo "== 4. GET authorize page (hidden fields)"
curl -s "$AUTH_URL" -o "$H"
ARGS=$(grep -o '<input type="hidden" name="[^"]*" value="[^"]*">' "$H" \
       | sed -E 's/.*name="([^"]*)" value="([^"]*)".*/\1=\2/' | tr '\n' '&' | sed 's/&$//')
[ -n "$ARGS" ] || fail "no hidden fields"
echo "   fields: $(echo "$ARGS" | tr '&' ' ' | cut -d= -f1 | tr '\n' ' ')"

echo "== 5. POST authorize (alice) -> 302 callback"
r=$(curl -s -o /dev/null -w "%{http_code}|%{redirect_url}" \
     -d "$ARGS&username=alice&password=alice123" "$AUTH_URL")
echo "   $r"
case "$r" in 302*code=*) ;; *) fail "step5";; esac
CB_URL="${r#*|}"

echo "== 6. callback -> land on SOPS"
r=$(curl -s -b "$J" -c "$J" -o /dev/null -w "%{http_code}|%{redirect_url}" "$CB_URL")
echo "   $r"
# follow remaining redirects (callback -> c_url)
LOC="${r#*|}"
CODE="${r%%|*}"
if [ "$CODE" = "302" ] || [ "$CODE" = "301" ]; then
  case "$LOC" in /*) LOC="$B$LOC";; esac
  r=$(curl -s -b "$J" -c "$J" -o /dev/null -w "%{http_code}|%{redirect_url}" "$LOC")
  echo "   -> $r"
  LOC="${r#*|}"; CODE="${r%%|*}"
  if [ "$CODE" = "302" ] || [ "$CODE" = "301" ]; then
    case "$LOC" in /*) LOC="$B$LOC";; esac
    r=$(curl -s -b "$J" -c "$J" -o /dev/null -w "%{http_code}" "$LOC")
    echo "   -> $r"; CODE="$r"
  fi
fi

echo "== 7. final page check"
PAGE=$(curl -s -b "$J" "$B/o/bk_sops/")
echo "$PAGE" | grep -q "Standard OPS" && echo "PASS: Standard OPS 200" || { echo "FAIL: page missing 'Standard OPS'"; echo "$PAGE" | head -c 300; exit 1; }
rm -f "$J" "$H"
