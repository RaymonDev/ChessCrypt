"""Optional authenticated symmetric encryption layer for ChessCrypt payloads."""

from __future__ import annotations

import hashlib
import hmac
import os

SALT_LEN = 8
TAG_LEN = 8
PBKDF2_ITERATIONS = 100_000


class CryptoError(ValueError):
    """Raised when payload authentication or decryption fails."""


def _derive_keys(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive 32-byte encryption key and 32-byte MAC key from a passphrase and salt."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=64,
    )
    return dk[:32], dk[32:]


def _xor_keystream(data: bytes, enc_key: bytes, salt: bytes) -> bytes:
    """XOR data with a SHA-256 CTR keystream."""
    out = bytearray(len(data))
    offset = 0
    counter = 0
    while offset < len(data):
        block = hashlib.sha256(enc_key + salt + counter.to_bytes(4, "big")).digest()
        chunk_len = min(len(block), len(data) - offset)
        for i in range(chunk_len):
            out[offset + i] = data[offset + i] ^ block[i]
        offset += chunk_len
        counter += 1
    return bytes(out)


def encrypt_payload(
    data: bytes,
    passphrase: str | None = None,
    *,
    salt: bytes | None = None,
) -> bytes:
    """Encrypt bytes with a passphrase, or return raw bytes if no passphrase is given.

    Encrypted frame format:
        [8-byte salt][ciphertext][8-byte HMAC-SHA256 tag]
    """
    if not passphrase:
        return data

    if salt is None:
        salt = os.urandom(SALT_LEN)
    elif len(salt) != SALT_LEN:
        raise ValueError(f"salt must be exactly {SALT_LEN} bytes")

    enc_key, mac_key = _derive_keys(passphrase, salt)
    ciphertext = _xor_keystream(data, enc_key, salt)
    tag = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()[:TAG_LEN]
    return salt + ciphertext + tag


def decrypt_payload(payload: bytes, passphrase: str | None = None) -> bytes:
    """Decrypt bytes with a passphrase, or return raw bytes if no passphrase is given."""
    if not passphrase:
        return payload

    if len(payload) < SALT_LEN + TAG_LEN:
        raise CryptoError("Encrypted payload is too short to contain salt and auth tag.")

    salt = payload[:SALT_LEN]
    tag = payload[-TAG_LEN:]
    ciphertext = payload[SALT_LEN:-TAG_LEN]

    enc_key, mac_key = _derive_keys(passphrase, salt)
    expected_tag = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()[:TAG_LEN]
    if not hmac.compare_digest(tag, expected_tag):
        raise CryptoError("Decryption failed: invalid passphrase or corrupted chess game.")

    return _xor_keystream(ciphertext, enc_key, salt)
