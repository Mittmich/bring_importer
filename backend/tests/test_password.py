"""Unit tests for password hashing helpers in ``api``."""

import passlib.exc
import pytest

import api


def test_get_password_hash_returns_string():
    h = api.get_password_hash("hunter2")
    assert isinstance(h, str)
    # bcrypt hashes are 60 chars
    assert len(h) == 60


def test_get_password_hash_uses_bcrypt():
    h = api.get_password_hash("hunter2")
    # bcrypt hashes start with $2a$, $2b$, $2y$, etc.
    assert h.startswith("$2")


def test_verify_password_correct():
    h = api.get_password_hash("correctpassword")
    assert api.verify_password("correctpassword", h) is True


def test_verify_password_wrong():
    h = api.get_password_hash("correctpassword")
    assert api.verify_password("wrongpassword", h) is False


def test_verify_password_non_bcrypt_hash_raises():
    """passlib raises ``UnknownHashError`` for hash formats it cannot identify.

    This is the actual behavior of ``passlib.context.CryptContext.verify`` —
    not a defect of our wrapper. Tests and callers must handle this exception
    explicitly if they want to treat unknown hashes as "no match".
    """
    with pytest.raises(passlib.exc.UnknownHashError):
        api.verify_password("any-password", "not-a-bcrypt-hash")


def test_verify_password_empty_against_real_hash():
    h = api.get_password_hash("realpassword")
    assert api.verify_password("", h) is False


def test_same_plaintext_produces_different_hashes():
    """Bcrypt salts its hashes, so the same plaintext should never produce identical hashes."""
    h1 = api.get_password_hash("samepassword")
    h2 = api.get_password_hash("samepassword")
    assert h1 != h2
    # but both should still verify
    assert api.verify_password("samepassword", h1)
    assert api.verify_password("samepassword", h2)
