"""Signing keys for the Ontada / iKnowMed app registered as Private (Asymmetric).

An asymmetric SMART client proves itself with a `private_key_jwt` assertion
signed by a key whose public half we publish as a JWKS. Ontada fetches that
JWKS from the Client JWKs URL entered at registration and uses it to verify
every token request — so no shared secret ever travels or sits in .env.

This keypair is deliberately separate from the Da Vinci payer keypair in
`app/davinci/keys.py`: same construction, own file, so either can be rotated
without disturbing the other. RSA-2048, signed RS384 (SMART-recommended).

The JWKS must be reachable over public HTTPS and MUST NOT sit behind the app's
own JWT auth — Ontada's authorization server is an anonymous fetcher.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .. import config

KEY_DIR = config.DATA_DIR / "keys"
KEY_DIR.mkdir(parents=True, exist_ok=True)
PRIVATE_PEM = KEY_DIR / "ontada_client_private.pem"

SIGNING_ALG = "RS384"


def _b64url_uint(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@lru_cache(maxsize=1)
def _private_key() -> rsa.RSAPrivateKey:
    if PRIVATE_PEM.exists():
        return serialization.load_pem_private_key(PRIVATE_PEM.read_bytes(),
                                                  password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    PRIVATE_PEM.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))
    PRIVATE_PEM.chmod(0o600)
    return key


@lru_cache(maxsize=1)
def kid() -> str:
    """RFC 7638 JWK thumbprint — the stable key id published in the JWKS."""
    pub = _private_key().public_key().public_numbers()
    jwk = {"e": _b64url_uint(pub.e), "kty": "RSA", "n": _b64url_uint(pub.n)}
    digest = hashlib.sha256(json.dumps(jwk, separators=(",", ":"),
                                       sort_keys=True).encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def private_pem() -> bytes:
    return _private_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())


def public_jwks() -> dict:
    """Public keys only — served at the registered Client JWKs URL."""
    pub = _private_key().public_key().public_numbers()
    return {"keys": [{
        "kty": "RSA",
        "use": "sig",
        "alg": SIGNING_ALG,
        "kid": kid(),
        "n": _b64url_uint(pub.n),
        "e": _b64url_uint(pub.e),
    }]}


def client_assertion(token_url: str) -> str:
    """Signed JWT proving client identity to Ontada's token endpoint.

    iss/sub are the client id Ontada issued; aud is the token endpoint itself,
    which is what stops an assertion being replayed against another server.
    """
    if not config.ONTADA_CLIENT_ID:
        raise RuntimeError("ONTADA_CLIENT_ID is not set — cannot sign an assertion.")
    now = int(time.time())
    return jwt.encode(
        {
            "iss": config.ONTADA_CLIENT_ID,
            "sub": config.ONTADA_CLIENT_ID,
            "aud": token_url,
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + 300,
        },
        private_pem(), algorithm=SIGNING_ALG, headers={"kid": kid()})
