"""Fernet-based encrypt / decrypt helpers for credential storage."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _make_fernet(base_key: str, user_id: int) -> Fernet:
    """Create a Fernet instance keyed to a specific user.

    The per-user key is derived as:
        SHA256(base_key + ":" + str(user_id))

    This ensures that even if the encrypted blob is leaked, it can only
    be decrypted with knowledge of both the server key and the user id.
    """
    raw = f"{base_key}:{user_id}".encode("utf-8")
    key_bytes = hashlib.sha256(raw).digest()  # 32 bytes
    encoded_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(encoded_key)


def encrypt_value(plaintext: str, fernet_key: str, user_id: int) -> str:
    """Encrypt a string value using a per-user derived Fernet key.

    Args:
        plaintext: The string to encrypt.
        fernet_key: Server-wide Fernet base key (from ENCRYPTION_KEY config).
        user_id: The user id to scope the key.

    Returns:
        Encrypted token as a string.
    """
    f = _make_fernet(fernet_key, user_id)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, fernet_key: str, user_id: int) -> str:
    """Decrypt a string value encrypted with :func:`encrypt_value`.

    Args:
        ciphertext: The encrypted token.
        fernet_key: Server-wide Fernet base key (from ENCRYPTION_KEY config).
        user_id: The user id used during encryption.

    Returns:
        Decrypted plaintext string.

    Raises:
        InvalidToken: If the key is wrong or data corrupted.
    """
    f = _make_fernet(fernet_key, user_id)
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


__all__ = ["encrypt_value", "decrypt_value", "InvalidToken"]
