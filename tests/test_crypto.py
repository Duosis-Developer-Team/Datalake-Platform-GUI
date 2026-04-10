"""Crypto helpers."""

from src.auth.crypto import fernet_encrypt, fernet_decrypt, hash_password, verify_password


def test_password_roundtrip():
    h = hash_password("secret")
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)


def test_fernet_roundtrip():
    t = fernet_encrypt("ldap-secret")
    assert fernet_decrypt(t) == "ldap-secret"
