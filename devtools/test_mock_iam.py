"""Unit tests for pure functions in mock_iam.py (no server, no network).

Run from this directory:
    python3 -m unittest test_mock_iam -v
"""

import base64
import json
import time
import unittest

import mock_iam


class Base64UrlTests(unittest.TestCase):
    def test_roundtrip_various_lengths(self):
        for raw in (b"", b"a", b"ab", b"abc", b"hello world", bytes(range(256))):
            self.assertEqual(mock_iam._b64url_decode(mock_iam._b64url(raw)), raw)

    def test_output_is_urlsafe_and_unpadded(self):
        out = mock_iam._b64url(b"+/?=\xff")
        self.assertNotIn("+", out)
        self.assertNotIn("/", out)
        self.assertNotIn("=", out)


class JwtEncodeTests(unittest.TestCase):
    def test_structure_and_header(self):
        tok = mock_iam.jwt_encode({"iss": "x", "exp": int(time.time()) + 60})
        h64, p64, s64 = tok.split(".")
        header = json.loads(mock_iam._b64url_decode(h64))
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(header["kid"], mock_iam.jwks()["keys"][0]["kid"])
        # token is url-safe and unpadded
        for seg in (h64, p64, s64):
            self.assertNotRegex(seg, r"[+/=]")


class JwtDecodeTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = {"iss": "http://t", "sub": "alice", "n": 1, "flag": True,
                   "exp": int(time.time()) + 60}
        self.assertEqual(mock_iam.jwt_decode(mock_iam.jwt_encode(payload)), payload)

    def test_missing_exp_rejected(self):
        with self.assertRaises(ValueError):
            mock_iam.jwt_decode(mock_iam.jwt_encode({"iss": "x", "sub": "alice"}))

    def test_tampered_payload_rejected(self):
        tok = mock_iam.jwt_encode({"iss": "x", "sub": "alice", "exp": int(time.time()) + 60})
        h64, p64, s64 = tok.split(".")
        forged_payload = mock_iam._b64url(json.dumps({"iss": "x", "sub": "mallory", "exp": int(time.time()) + 60}).encode())
        with self.assertRaises(ValueError):
            mock_iam.jwt_decode("%s.%s.%s" % (h64, forged_payload, s64))

    def test_tampered_signature_rejected(self):
        tok = mock_iam.jwt_encode({"iss": "x", "exp": int(time.time()) + 60})
        h64, p64, s64 = tok.split(".")
        bad_sig = ("A" if s64[0] != "A" else "B") + s64[1:]
        with self.assertRaises(ValueError):
            mock_iam.jwt_decode("%s.%s.%s" % (h64, p64, bad_sig))

    def test_expired_rejected(self):
        tok = mock_iam.jwt_encode({"iss": "x", "exp": int(time.time()) - 10})
        with self.assertRaises(ValueError):
            mock_iam.jwt_decode(tok)

    def test_garbage_rejected(self):
        for bad in ("", "abc", "a.b", "a.b.c", "...."):
            with self.assertRaises(ValueError):
                mock_iam.jwt_decode(bad)


class JwksTests(unittest.TestCase):
    def test_structure(self):
        doc = mock_iam.jwks()
        self.assertEqual(len(doc["keys"]), 1)
        k = doc["keys"][0]
        self.assertEqual(k["kty"], "RSA")
        self.assertEqual(k["use"], "sig")
        self.assertEqual(k["alg"], "RS256")
        self.assertTrue(k["kid"])
        # n decodes to a positive integer, e is 65537 (AQAB)
        n = int.from_bytes(mock_iam._b64url_decode(k["n"]), "big")
        e = int.from_bytes(mock_iam._b64url_decode(k["e"]), "big")
        self.assertGreater(n.bit_length(), 2000)
        self.assertEqual(e, 65537)

    def test_kid_is_stable_across_calls(self):
        self.assertEqual(mock_iam.jwks()["keys"][0]["kid"],
                         mock_iam.jwks()["keys"][0]["kid"])


class ClaimsTests(unittest.TestCase):
    def test_content(self):
        c = mock_iam._claims("alice")
        self.assertEqual(c["iss"], mock_iam.ISSUER)
        self.assertEqual(c["sub"], "alice")
        self.assertEqual(c["aud"], mock_iam.CLIENT_ID)
        self.assertEqual(c["preferred_username"], "alice")
        self.assertEqual(c["email"], mock_iam.TEST_USERS["alice"]["email"])
        self.assertEqual(c["groups"], ["SOPS-ADMIN"])
        self.assertEqual(c["exp"] - c["iat"], mock_iam.TOKEN_TTL)

    def test_groups_list_is_a_copy(self):
        c = mock_iam._claims("bob")
        c["groups"].append("EVIL-GROUP")
        self.assertNotIn("EVIL-GROUP", mock_iam.TEST_USERS["bob"]["groups"])
        self.assertNotIn("EVIL-GROUP", mock_iam._claims("bob")["groups"])

    def test_unknown_user_raises(self):
        with self.assertRaises(KeyError):
            mock_iam._claims("nobody")


if __name__ == "__main__":
    unittest.main(verbosity=2)
