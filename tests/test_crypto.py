"""Unit tests for the symmetric encryption layer (`chesscrypt.crypto`)."""

import pytest
from chesscrypt.crypto import CryptoError, decrypt_payload, encrypt_payload


def test_passthrough_without_passphrase():
    raw = b"Hello World"
    assert encrypt_payload(raw, None) == raw
    assert encrypt_payload(raw, "") == raw
    assert decrypt_payload(raw, None) == raw
    assert decrypt_payload(raw, "") == raw


def test_encrypt_decrypt_roundtrip_with_passphrase():
    raw = b"Hello World"
    encrypted = encrypt_payload(raw, passphrase="correct-horse-battery-staple")
    assert encrypted != raw
    assert len(encrypted) == len(raw) + 16  # 8B salt + 11B data + 8B HMAC tag
    decrypted = decrypt_payload(encrypted, passphrase="correct-horse-battery-staple")
    assert decrypted == raw


def test_deterministic_salt_produces_reproducible_ciphertext():
    salt = b"12345678"
    c1 = encrypt_payload(b"Hello World", passphrase="secret", salt=salt)
    c2 = encrypt_payload(b"Hello World", passphrase="secret", salt=salt)
    assert c1 == c2


def test_wrong_passphrase_raises_crypto_error():
    encrypted = encrypt_payload(b"Hello World", passphrase="right-password")
    with pytest.raises(CryptoError, match="invalid passphrase"):
        decrypt_payload(encrypted, passphrase="wrong-password")


def test_tampered_ciphertext_raises_crypto_error():
    encrypted = bytearray(encrypt_payload(b"Hello World", passphrase="secret"))
    encrypted[10] ^= 0xFF
    with pytest.raises(CryptoError):
        decrypt_payload(bytes(encrypted), passphrase="secret")


def test_too_short_payload_raises_crypto_error():
    with pytest.raises(CryptoError, match="too short"):
        decrypt_payload(b"short", passphrase="secret")
