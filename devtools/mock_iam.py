#!/usr/bin/env python3
"""
Mock company IAM (OIDC Provider) for local self-testing of BlueKing SOPS integration.

Simulates the company IAM & IDM endpoints used by the SOPS login integration:

  GET  /.well-known/openid-configuration   discovery document
  GET/POST /authorize                      auth endpoint (login form -> authorization code)
  POST /token                              code exchange -> id_token (JWT RS256) + access_token
  GET  /jwks.json                          public keys for id_token verification
  GET  /userinfo                           claims for a Bearer access_token
  POST /introspect                         token introspection (for runtime-check mode)

Usage:
    python3 mock_iam.py              # serves on http://localhost:5556
    pkill -f mock_iam.py             # stop

Test users (see TEST_USERS below):
    alice / alice123  -> groups: ["SOPS-ADMIN"]
    bob   / bob123    -> groups: ["SOPS-PM-blueking", "SOPS-VIEWER"]

Client credentials (as a confidential OIDC client):
    client_id=sops-local  client_secret=sops-local-secret
    redirect_uri=http://localhost:8080/o/bk_sops/login/oauth/callback/

RSA keypair is generated on first start and persisted to ./mock_iam_data/
so JWKS stays stable across restarts (bkauth caches JWKS).
"""

import base64
import hashlib
import json
import os
import time
import uuid

from flask import Flask, request, redirect, make_response
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# ---------------------------------------------------------------- config

HOST, PORT = "0.0.0.0", 5556   # 0.0.0.0 so containers reach it via the bridge gateway
ISSUER = os.environ.get("MOCK_ISSUER", "http://localhost:5556")
CLIENT_ID = os.environ.get("MOCK_CLIENT_ID", "sops-local")
CLIENT_SECRET = os.environ.get("MOCK_CLIENT_SECRET", "sops-local-secret")
REDIRECT_URI = os.environ.get(
    "MOCK_REDIRECT_URI", "http://localhost:8080/o/bk_sops/login/oauth/callback/"
)
TOKEN_TTL = 3600          # seconds
CODE_TTL = 300            # seconds

# username -> {password, email, groups}
TEST_USERS = {
    "alice": {
        "password": "alice123",
        "email": "alice@example.corp",
        "groups": ["SOPS-ADMIN"],
    },
    "bob": {
        "password": "bob123",
        "email": "bob@example.corp",
        "groups": ["SOPS-PM-blueking", "SOPS-VIEWER"],
    },
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_iam_data")

# ---------------------------------------------------------------- keys / jwt

def _load_or_create_key():
    os.makedirs(DATA_DIR, exist_ok=True)
    pem = os.path.join(DATA_DIR, "mock_iam_rsa.pem")
    if os.path.exists(pem):
        with open(pem, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(pem, "wb") as fh:
            fh.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        os.chmod(pem, 0o600)
    return key


_PRIVKEY = _load_or_create_key()
_KID = hashlib.sha256(
    _PRIVKEY.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
).hexdigest()[:16]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jwt_encode(payload: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": _KID}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = _PRIVKEY.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return signing_input + "." + _b64url(sig)


def jwt_decode(token: str) -> dict:
    """Verify signature + exp; raise ValueError on any failure."""
    try:
        h64, p64, s64 = token.split(".")
        sig = _b64url_decode(s64)
        _PRIVKEY.public_key().verify(sig, (h64 + "." + p64).encode(),
                                     padding.PKCS1v15(), hashes.SHA256())
        payload = json.loads(_b64url_decode(p64))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid token: %r" % exc)


def jwks() -> dict:
    pub = _PRIVKEY.public_key().public_numbers()
    n = _b64url(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big"))
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256",
                      "kid": _KID, "n": n, "e": _b64url(pub.e.to_bytes(3, "big"))}]}

# ---------------------------------------------------------------- state

AUTH_CODES = {}  # code -> {user, redirect_uri, exp}

# ---------------------------------------------------------------- app

app = Flask(__name__)


def _claims(user: str) -> dict:
    u = TEST_USERS[user]
    now = int(time.time())
    return {"iss": ISSUER, "sub": user, "aud": CLIENT_ID, "iat": now,
            "exp": now + TOKEN_TTL, "preferred_username": user,
            "email": u["email"], "groups": list(u["groups"])}


LOGIN_PAGE = """<html><body style="font-family:sans-serif;max-width:22em;margin:4em auto">
<h3>Company IAM (mock) - Sign in</h3>
<p style="color:#888">users: alice/alice123 (SOPS-ADMIN), bob/bob123 (PM+VIEWER)</p>
<form method="post" action="/authorize">
  {hidden}
  <input name="username" placeholder="username" required style="width:100%;margin:4px 0">
  <input name="password" type="password" placeholder="password" required style="width:100%;margin:4px 0">
  <button type="submit" style="width:100%;margin-top:8px">Sign in</button>
</form></body></html>"""


@app.route("/authorize", methods=["GET", "POST"])
def authorize():
    if request.method == "GET":
        if request.args.get("client_id") != CLIENT_ID:
            return "invalid client_id", 400
        hidden = "".join(
            '<input type="hidden" name="%s" value="%s">' % (k, v)
            for k, v in request.args.items()
        )
        return LOGIN_PAGE.format(hidden=hidden)

    user = request.form.get("username", "")
    if TEST_USERS.get(user, {}).get("password") != request.form.get("password"):
        return "invalid credentials", 401

    redirect_uri = request.form.get("redirect_uri") or REDIRECT_URI
    code = uuid.uuid4().hex
    AUTH_CODES[code] = {"user": user, "redirect_uri": redirect_uri,
                        "exp": time.time() + CODE_TTL}
    sep = "&" if "?" in redirect_uri else "?"
    location = "%s%scode=%s&state=%s" % (
        redirect_uri, sep, code, request.form.get("state", ""))
    resp = make_response("", 302)
    resp.headers["Location"] = location
    return resp


@app.route("/token", methods=["POST"])
def token():
    if request.form.get("grant_type") != "authorization_code":
        return {"error": "unsupported_grant_type"}, 400
    if request.form.get("client_id") != CLIENT_ID or \
       request.form.get("client_secret") != CLIENT_SECRET:
        return {"error": "invalid_client"}, 401

    code = request.form.get("code", "")
    entry = AUTH_CODES.pop(code, None)
    if not entry or entry["exp"] < time.time():
        return {"error": "invalid_grant"}, 400
    if request.form.get("redirect_uri", entry["redirect_uri"]) != entry["redirect_uri"]:
        return {"error": "invalid_grant"}, 400

    claims = _claims(entry["user"])
    if request.form.get("nonce"):
        claims["nonce"] = request.form["nonce"]
    return {"access_token": jwt_encode(claims), "id_token": jwt_encode(claims),
            "token_type": "Bearer", "expires_in": TOKEN_TTL}


@app.route("/jwks.json")
def jwks_endpoint():
    return jwks()


@app.route("/userinfo")
def userinfo():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"error": "missing bearer token"}, 401
    try:
        claims = jwt_decode(auth[7:])
    except ValueError as exc:
        return {"error": str(exc)}, 401
    return {k: claims[k] for k in ("sub", "preferred_username", "email", "groups")}


@app.route("/introspect", methods=["POST"])
def introspect():
    if request.form.get("client_id") != CLIENT_ID or \
       request.form.get("client_secret") != CLIENT_SECRET:
        return {"error": "invalid_client"}, 401
    try:
        claims = jwt_decode(request.form.get("token", ""))
    except ValueError:
        return {"active": False}
    return {"active": True, "sub": claims["sub"],
            "groups": claims["groups"], "exp": claims["exp"]}


@app.route("/.well-known/openid-configuration")
def discovery():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "userinfo_endpoint": ISSUER + "/userinfo",
        "jwks_uri": ISSUER + "/jwks.json",
        "introspection_endpoint": ISSUER + "/introspect",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "claims_supported": ["sub", "preferred_username", "email", "groups"],
    }


if __name__ == "__main__":
    print("Mock company IAM")
    print("  issuer      :", ISSUER)
    print("  client      :", CLIENT_ID, "/", CLIENT_SECRET)
    print("  redirect_uri:", REDIRECT_URI)
    print("  test users  :", ", ".join(
        "%s(%s)" % (u, ",".join(v["groups"])) for u, v in TEST_USERS.items()))
    app.run(host=HOST, port=PORT, debug=False)
