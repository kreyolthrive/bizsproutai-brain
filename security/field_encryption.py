"""
Field-Level Payload Encryption (FLE) for the Python backend.

AES-256-GCM application-layer encryption and decryption matching the wire format:
enc:v1:<base64_iv>:<base64_ciphertext>:<base64_tag>

Production encryption is fail-closed: PAYLOAD_ENCRYPTION_KEY must be configured
for encrypted payloads. There is intentionally no hard-coded fallback secret.
"""

import base64
import hashlib
import os
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FLE_PREFIX = "enc:v1:"
DEFAULT_APP_SALT = b"bizsprout-fle-salt-2026"
MIN_SECRET_LENGTH = 32


def _resolve_secret(passphrase: Optional[str] = None) -> str:
    secret = passphrase or os.getenv("PAYLOAD_ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("PAYLOAD_ENCRYPTION_KEY is required for encrypted payloads")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"PAYLOAD_ENCRYPTION_KEY must be at least {MIN_SECRET_LENGTH} characters"
        )
    return secret


def derive_fle_key(passphrase: Optional[str] = None) -> bytes:
    """Derive a 256-bit AES key using PBKDF2-HMAC-SHA256."""
    secret = _resolve_secret(passphrase)
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        DEFAULT_APP_SALT,
        iterations=100_000,
        dklen=32,
    )


def is_encrypted_field(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(FLE_PREFIX)


def encrypt_sensitive_field(plaintext: str, passphrase: Optional[str] = None) -> str:
    if not plaintext or not isinstance(plaintext, str):
        return plaintext

    key = derive_fle_key(passphrase)
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    encrypted = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext = encrypted[:-16]
    tag = encrypted[-16:]

    return (
        f"{FLE_PREFIX}"
        f"{base64.b64encode(iv).decode('ascii')}:"
        f"{base64.b64encode(ciphertext).decode('ascii')}:"
        f"{base64.b64encode(tag).decode('ascii')}"
    )


def decrypt_sensitive_field(encrypted_str: str, passphrase: Optional[str] = None) -> str:
    """
    Decrypt an FLE value. Plaintext values are returned unchanged for backwards
    compatibility; malformed/encrypted values fail closed instead of being
    forwarded downstream as if decryption had succeeded.
    """
    if not is_encrypted_field(encrypted_str):
        return encrypted_str

    raw = encrypted_str[len(FLE_PREFIX):]
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError("Malformed encrypted payload")

    try:
        iv = base64.b64decode(parts[0], validate=True)
        ciphertext = base64.b64decode(parts[1], validate=True)
        tag = base64.b64decode(parts[2], validate=True)
    except Exception as exc:
        raise ValueError("Malformed encrypted payload encoding") from exc

    if len(iv) != 12 or len(tag) != 16:
        raise ValueError("Malformed AES-GCM payload")

    key = derive_fle_key(passphrase)
    aesgcm = AESGCM(key)
    try:
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception as exc:
        raise ValueError("Encrypted payload authentication failed") from exc

    return decrypted_bytes.decode("utf-8")


def decrypt_payload_fields(
    payload: Dict[str, Any],
    sensitive_keys: List[str],
    passphrase: Optional[str] = None,
) -> Dict[str, Any]:
    result = dict(payload)
    for key in sensitive_keys:
        if (
            key in result
            and isinstance(result[key], str)
            and is_encrypted_field(result[key])
        ):
            result[key] = decrypt_sensitive_field(result[key], passphrase)
    return result
