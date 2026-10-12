"""
WSGI config for testapp3 project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""

import os

from blueapps.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

application = get_wsgi_application()


# --- PATCH: WSGI static file middleware -------------------------------------
# uwsgi static-map/static-map2 do not intercept requests in this
# mount + manage-script-name setup, so serve static files at the WSGI layer.
try:
    import mimetypes

    _STATIC_ROOT = '/data/app/code/bk_sops/static'
    _PREFIXES = ('/o/bk_sops/static/', '/static/')

    def _wsgi_static_wrapper(app):
        def _handler(environ, start_response):
            path = environ.get('PATH_INFO', '')
            for prefix in _PREFIXES:
                if path.startswith(prefix):
                    rel = path[len(prefix):]
                    full = os.path.normpath(os.path.join(_STATIC_ROOT, rel))
                    if full.startswith(_STATIC_ROOT) and os.path.isfile(full):
                        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
                        with open(full, 'rb') as fh:
                            data = fh.read()
                        start_response('200 OK', [
                            ('Content-Type', ctype),
                            ('Content-Length', str(len(data))),
                        ])
                        return [data]
                    break
            return app(environ, start_response)
        return _handler

    application = _wsgi_static_wrapper(application)
except Exception as _e:
    import logging

    logging.getLogger('root').error('wsgi static wrapper failed: %r' % _e)
# --- END PATCH ---------------------------------------------------------------


# --- PATCH: OIDC login (company IAM / IDM) -----------------------------------
# WSGI-level OIDC Relying Party, so SOPS can authenticate against the company
# IAM without touching the (encrypted) bkauth / blueapps auth chain:
#
#   GET /login/oauth/login/     redirect to the IAM /authorize endpoint,
#                               keeping "next" in a short-lived cookie
#   GET /login/oauth/callback/  exchange the code for an id_token, verify it
#                               (RS256 via cached JWKS, stdlib-only RSA math),
#                               then seed the paas-native contract so the
#                               existing blueapps bk_token chain works as-is:
#                                 * open_paas.account_bkuser  (user profile,
#                                   consumed by login's get_user via ESB)
#                                 * open_paas.login_bktoken   (token registry,
#                                   consumed by login's accounts/is_login)
#                               and finally set the bk_token cookie.
#
# Config comes from supervisord environment (see patches/bkce-sops/conf/).
# Works with devtools/mock_iam.py or any standard OIDC provider.
try:
    import base64 as _b64mod
    import hashlib as _hashlib
    import json as _json
    import logging as _logging
    import secrets as _secrets
    import time as _time
    import urllib.parse as _up
    import urllib.request as _ur

    _OIDC = {
        'issuer': os.environ.get('BK_OIDC_ISSUER', 'http://localhost:5556'),
        # server-side base URL (reached from inside the container; the mac
        # host is the bridge gateway of the fixed compose subnet)
        'server': os.environ.get('BK_OIDC_SERVER', 'http://172.18.107.1:5556'),
        'client_id': os.environ.get('BK_OIDC_CLIENT_ID', 'sops-local'),
        'client_secret': os.environ.get('BK_OIDC_CLIENT_SECRET', 'sops-local-secret'),
        'redirect_uri': os.environ.get(
            'BK_OIDC_REDIRECT_URI',
            'http://localhost:8080/o/bk_sops/login/oauth/callback/'),
        'admin_groups': [g.strip() for g in
                         os.environ.get('BK_OIDC_ADMIN_GROUPS', 'SOPS-ADMIN').split(',')
                         if g.strip()],
        'site_url': os.environ.get('BK_OIDC_SITE_URL', '/o/bk_sops/'),
        'db_host': os.environ.get('DB_HOST', 'mysql-default.service.consul'),
        'db_user': os.environ.get('DB_USERNAME', 'paas'),
        'db_pass': os.environ.get('DB_PASSWORD', ''),
        'paas_db': os.environ.get('BK_OIDC_PAAS_DB', 'open_paas'),
        # usermgr's own db — login's get_user (via ESB) reads users from here
        'usermgr_db': os.environ.get('BK_OIDC_USERMGR_DB', 'bk_user_manage'),
        # SECRET_KEY of the paas login app — bk_token is
        # urlsafe_b64(AES-128-ECB(MD5(SECRET_KEY), "expire|user|salt"))
        'login_secret_key': os.environ.get('BK_LOGIN_SECRET_KEY', 'J04sJ8hN3Wsq'),
    }
    _SHA256_DIGESTINFO = bytes.fromhex(
        '3031300d060960864801650304020105000420')
    _JWKS_CACHE = {'ts': 0.0, 'keys': {}}

    _oauth_log = _logging.getLogger('root')

    def _b64url_decode(seg):
        return _b64mod.urlsafe_b64decode(seg + '=' * (-len(seg) % 4))

    def _jwks_keys():
        now = _time.time()
        if now - _JWKS_CACHE['ts'] > 3600:
            url = _OIDC['server'] + '/jwks.json'
            data = _json.loads(_ur.urlopen(url, timeout=5).read().decode('utf-8'))
            keys = {}
            for k in data.get('keys', []):
                if k.get('kty') == 'RSA' and k.get('alg', 'RS256') == 'RS256':
                    keys[k.get('kid', '')] = (
                        int.from_bytes(_b64url_decode(k['n']), 'big'),
                        int.from_bytes(_b64url_decode(k['e']), 'big'),
                    )
            _JWKS_CACHE['ts'] = now
            _JWKS_CACHE['keys'] = keys
        return _JWKS_CACHE['keys']

    def _verify_id_token(id_token):
        """Return claims dict; raise ValueError on any problem."""
        h64, p64, s64 = id_token.split('.')
        header = _json.loads(_b64url_decode(h64).decode('utf-8'))
        if header.get('alg') != 'RS256':
            raise ValueError('unexpected alg %r' % header.get('alg'))
        try:
            n, e = _jwks_keys()[header.get('kid', '')]
        except KeyError:
            raise ValueError('unknown kid %r' % header.get('kid'))
        sig = _b64url_decode(s64)
        k = (n.bit_length() + 7) // 8
        em = pow(int.from_bytes(sig, 'big'), e, n).to_bytes(k, 'big')
        digest = _hashlib.sha256((h64 + '.' + p64).encode('ascii')).digest()
        ff_len = k - 3 - len(_SHA256_DIGESTINFO) - len(digest)
        if ff_len < 8:
            raise ValueError('bad modulus size')
        expected = (b'\x00\x01' + b'\xff' * ff_len + b'\x00'
                    + _SHA256_DIGESTINFO + digest)
        if em != expected:
            raise ValueError('bad signature')
        claims = _json.loads(_b64url_decode(p64).decode('utf-8'))
        if claims.get('iss') != _OIDC['issuer']:
            raise ValueError('iss mismatch')
        aud = claims.get('aud')
        if isinstance(aud, list):
            if _OIDC['client_id'] not in aud:
                raise ValueError('aud mismatch')
        elif aud != _OIDC['client_id']:
            raise ValueError('aud mismatch')
        if int(claims.get('exp', 0)) < _time.time():
            raise ValueError('token expired')
        return claims

    def _exchange_code(code):
        body = _up.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _OIDC['redirect_uri'],
            'client_id': _OIDC['client_id'],
            'client_secret': _OIDC['client_secret'],
        }).encode('utf-8')
        req = _ur.Request(_OIDC['server'] + '/token', data=body)
        resp = _ur.urlopen(req, timeout=10)
        return _json.loads(resp.read().decode('utf-8'))

    def _mint_bk_token(username):
        """Forge a bk_token exactly the way paas login (bkaccount.encryption)
        does: plain = "expire_time|username|salt8", AES-128-ECB with
        key = MD5(login SECRET_KEY), PKCS#5 padding, urlsafe-b64, no '='."""
        from Crypto.Cipher import AES
        import hashlib

        alphabet = ('abcdefghijklmnopqrstuvwxyz'
                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    '0123456789')
        salt8 = ''.join(_secrets.choice(alphabet) for _ in range(8))
        expire = int(_time.time()) + 86400  # BK_COOKIE_AGE
        plain = '%s|%s|%s' % (expire, username, salt8)
        pad = 16 - (len(plain) % 16)
        plain += pad * chr(pad)
        key = hashlib.md5(_OIDC['login_secret_key'].encode('utf-8')).digest()
        cipher = AES.new(key, AES.MODE_ECB)
        raw = cipher.encrypt(plain.encode('utf-8'))
        return _b64mod.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    def _seed_paas_user(username, chname, email, role, token, ttl):
        """Write the paas-native rows so login's is_login/get_user accept us."""
        import MySQLdb

        conn = MySQLdb.connect(
            host=_OIDC['db_host'], user=_OIDC['db_user'],
            passwd=_OIDC['db_pass'], db=_OIDC['paas_db'], charset='utf8')
        try:
            cur = conn.cursor()
            is_admin = 1 if role == '1' else 0
            cur.execute(
                "INSERT INTO account_bkuser"
                " (password, last_login, is_superuser, username, chname,"
                "  company, qq, phone, email, is_staff, date_joined, role)"
                " VALUES ('', NOW(), %s, %s, %s, '', '', '', %s, %s, NOW(), %s)"
                " ON DUPLICATE KEY UPDATE chname=VALUES(chname),"
                " email=VALUES(email), role=VALUES(role),"
                " is_superuser=VALUES(is_superuser), is_staff=VALUES(is_staff),"
                " last_login=NOW()",
                (is_admin, username, chname, email, is_admin, role))
            # usermgr db (no `role` column) — source for ESB bk_login.get_user
            cur.execute(
                "INSERT INTO %s.account_bkuser"
                " (password, last_login, is_superuser, username, chname,"
                "  company, qq, phone, email, is_staff, date_joined)"
                " VALUES ('', NOW(), %%s, %%s, %%s, '', '', '', %%s, %%s, NOW())"
                " ON DUPLICATE KEY UPDATE chname=VALUES(chname),"
                " email=VALUES(email),"
                " is_superuser=VALUES(is_superuser), is_staff=VALUES(is_staff),"
                " last_login=NOW()" % _OIDC['usermgr_db'],
                (is_admin, username, chname, email, is_admin))
            cur.execute(
                "INSERT INTO login_bktoken (token, is_logout, inactive_expire_time)"
                " VALUES (%s, 0, %s)",
                (token, int(_time.time()) + ttl))
            conn.commit()
        finally:
            conn.close()

    def _cookies(environ):
        out = {}
        for part in environ.get('HTTP_COOKIE', '').split(';'):
            k, _, v = part.strip().partition('=')
            if k:
                out[k] = v
        return out

    def _wsgi_resp(start_response, status, headers, body=b''):
        start_response(status, [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Content-Length', str(len(body))),
        ] + headers)
        return [body]

    def _handle_oauth_login(environ, start_response):
        qs = _up.parse_qs(environ.get('QUERY_STRING', ''))
        c_url = (qs.get('c_url') or [_OIDC['site_url']])[0]
        # the 401 handler passes an absolute c_url — accept it when it points
        # at our own host, keep the path for the post-login redirect
        if c_url.startswith('http://') or c_url.startswith('https://'):
            parsed = _up.urlparse(c_url)
            c_url = (parsed.path + ('?' + parsed.query if parsed.query else '')
                     if parsed.netloc == _up.urlparse(_OIDC['redirect_uri']).netloc
                     else _OIDC['site_url'])
        if not c_url.startswith('/') or c_url.startswith('//'):
            c_url = _OIDC['site_url']
        state = _secrets.token_urlsafe(16)
        params = _up.urlencode({
            'response_type': 'code',
            'client_id': _OIDC['client_id'],
            'redirect_uri': _OIDC['redirect_uri'],
            'scope': 'openid',
            'state': state,
        })
        headers = [
            ('Location', _OIDC['issuer'] + '/authorize?' + params),
            ('Set-Cookie', 'oauth_state=%s; Path=/; Max-Age=600; HttpOnly' % state),
            ('Set-Cookie', 'oauth_next=%s; Path=/; Max-Age=600; HttpOnly' % _up.quote(c_url, safe='')),
        ]
        return _wsgi_resp(start_response, '302 Found', headers)

    def _handle_oauth_callback(environ, start_response):
        qs = _up.parse_qs(environ.get('QUERY_STRING', ''))
        cookies = _cookies(environ)
        code = (qs.get('code') or [''])[0]
        state = (qs.get('state') or [''])[0]
        if not code:
            return _wsgi_resp(start_response, '400 Bad Request', [],
                              b'oidc: missing code')
        if not state or state != cookies.get('oauth_state'):
            return _wsgi_resp(start_response, '400 Bad Request', [],
                              b'oidc: state mismatch')
        try:
            tokens = _exchange_code(code)
            claims = _verify_id_token(tokens.get('id_token', ''))
        except Exception as exc:
            _oauth_log.exception('oidc callback failed: %r', exc)
            return _wsgi_resp(start_response, '502 Bad Gateway', [],
                              ('oidc: %s' % exc).encode('utf-8'))

        username = claims.get('preferred_username') or claims.get('sub', '')
        if not username:
            return _wsgi_resp(start_response, '400 Bad Request', [],
                              b'oidc: no subject in token')
        email = claims.get('email', '')
        chname = claims.get('chname') or claims.get('nickname') or username
        groups = claims.get('groups') or []
        role = '1' if any(g in _OIDC['admin_groups'] for g in groups) else '0'
        bk_token = _mint_bk_token(username)
        _seed_paas_user(username, chname, email, role, bk_token, 86400)

        c_url = _up.unquote(cookies.get('oauth_next', '')) or _OIDC['site_url']
        if not c_url.startswith('/') or c_url.startswith('//'):
            c_url = _OIDC['site_url']
        headers = [
            ('Location', c_url),
            ('Set-Cookie', 'bk_token=%s; Path=/; Max-Age=86400; HttpOnly' % bk_token),
            ('Set-Cookie', 'oauth_state=; Path=/; Max-Age=0; HttpOnly'),
            ('Set-Cookie', 'oauth_next=; Path=/; Max-Age=0; HttpOnly'),
        ]
        return _wsgi_resp(start_response, '302 Found', headers)

    def _wsgi_oauth_wrapper(app):
        def _handler(environ, start_response):
            path = environ.get('PATH_INFO', '')
            if path.startswith('/o/bk_sops'):
                path = path[len('/o/bk_sops'):]
            if path == '/login/oauth/login/':
                return _handle_oauth_login(environ, start_response)
            if path == '/login/oauth/callback/':
                return _handle_oauth_callback(environ, start_response)
            return app(environ, start_response)
        return _handler

    application = _wsgi_oauth_wrapper(application)
except Exception as _e:
    _logging.getLogger('root').error('wsgi oauth wrapper failed: %r' % _e)
# --- END PATCH ---------------------------------------------------------------


# --- PATCH: root redirect ----------------------------------------------------
# http://localhost:8080/ (the bare host) is not a SOPS route — bounce it to the
# canonical /o/bk_sops/ entry so the browser lands on the app instead of a
# Django 404/login-redirect. SCRIPT_NAME disambiguates the real root from the
# mount-stripped root (/o/bk_sops/ also yields PATH_INFO='/' but keeps
# SCRIPT_NAME='/o/bk_sops', which we must NOT redirect or we'd loop forever).
def _wsgi_root_redirect(app):
    def _handler(environ, start_response):
        if (not environ.get('SCRIPT_NAME', '')
                and environ.get('PATH_INFO', '') in ('', '/')):
            start_response('302 Found', [
                ('Location', '/o/bk_sops/'),
                ('Content-Length', '0'),
            ])
            return [b'']
        return app(environ, start_response)
    return _handler

application = _wsgi_root_redirect(application)
# --- END PATCH ---------------------------------------------------------------


# --- PATCH: standalone auth (2-container stack, no paas container) -----------
# With paas/login/ESB removed, the blueapps bk_token auth chain is answered
# locally instead of over HTTP to the (gone) paas container:
#   * TokenBackend.verify_bk_token -> decrypt bk_token in-process
#     (AES-128-ECB, key = MD5(login SECRET_KEY) — same recipe paas login
#     uses), check expiry. No open_paas.login_bktoken row or HTTP needed.
#   * TokenBackend.get_user_info   -> read the open_paas.account_bkuser row
#     seeded by the OIDC callback. No ESB / usermgr call needed.
#   * ConfFixture 401 login redirects (LOGIN_URL / LOGIN_PLAIN_URL, read via
#     the BLUEAPPS_ACCOUNT_* settings-first override) point at our own OIDC
#     entry instead of the removed paas login page.
try:
    from django.conf import settings as _dj_settings

    def _standalone_verify_bk_token(bk_token, request=None):
        try:
            from Crypto.Cipher import AES
            import hashlib
            raw = _b64url_decode(bk_token)
            if not raw or len(raw) % 16:
                return False, None
            key = hashlib.md5(_OIDC['login_secret_key'].encode('utf-8')).digest()
            plain = AES.new(key, AES.MODE_ECB).decrypt(raw)
            pad = plain[-1]
            if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
                return False, None
            expire, username, _salt = plain[:-pad].decode('utf-8').split('|', 2)
            if int(expire) < _time.time():
                return False, None
            return True, username
        except Exception:
            return False, None

    def _standalone_get_user_info(bk_token):
        ok, username = _standalone_verify_bk_token(bk_token)
        if not ok:
            return False, {}
        try:
            import MySQLdb
            conn = MySQLdb.connect(
                host=_OIDC['db_host'], user=_OIDC['db_user'],
                passwd=_OIDC['db_pass'], db=_OIDC['paas_db'], charset='utf8')
            try:
                cur = conn.cursor()
                cur.execute(
                    'SELECT chname, email, role FROM account_bkuser'
                    ' WHERE username=%s', (username,))
                row = cur.fetchone()
            finally:
                conn.close()
        except Exception as exc:
            _oauth_log.exception('standalone get_user_info db failed: %r', exc)
            return False, {}
        if not row:
            return False, {}
        chname, email, role = row
        return True, {
            'username': username, 'chname': chname or username,
            'email': email or '', 'role': str(role), 'qq': '', 'phone': '',
            'wx_userid': '', 'language': 'en', 'time_zone': 'Asia/Shanghai',
        }

    from blueapps.account.components.bk_token.backends import TokenBackend
    TokenBackend.verify_bk_token = staticmethod(_standalone_verify_bk_token)
    TokenBackend.get_user_info = staticmethod(_standalone_get_user_info)

    _login_base = _OIDC['redirect_uri'].split('/login/oauth/callback/')[0]
    _dj_settings.BLUEAPPS_ACCOUNT_LOGIN_URL = _login_base + '/login/oauth/login/'
    _dj_settings.BLUEAPPS_ACCOUNT_LOGIN_PLAIN_URL = _login_base + '/login/oauth/login/'
except Exception as _e:
    _logging.getLogger('root').error('wsgi standalone auth failed: %r' % _e)
# --- END PATCH ---------------------------------------------------------------
