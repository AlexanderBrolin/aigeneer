"""Fernet-based encryption for secrets stored in the database."""

import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_key(secret_key: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret."""
    digest = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plain: str, secret_key: str) -> str:
    """Encrypt a plaintext string, return base64-encoded ciphertext."""
    f = Fernet(_derive_key(secret_key))
    return f.encrypt(plain.encode()).decode()


def decrypt_value(cipher: str, secret_key: str) -> str:
    """Decrypt a base64-encoded ciphertext back to plaintext."""
    f = Fernet(_derive_key(secret_key))
    return f.decrypt(cipher.encode()).decode()
