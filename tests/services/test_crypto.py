from app.services.crypto import decrypt_value, encrypt_value


def test_encrypt_decrypt_round_trip():
    secret_key = "test-secret-key-for-fernet-32!!"
    plain = "sk-aitunnel-very-secret-key"
    encrypted = encrypt_value(plain, secret_key)
    assert encrypted != plain
    decrypted = decrypt_value(encrypted, secret_key)
    assert decrypted == plain


def test_encrypt_produces_different_ciphertext():
    secret_key = "test-secret-key-for-fernet-32!!"
    plain = "my-secret"
    e1 = encrypt_value(plain, secret_key)
    e2 = encrypt_value(plain, secret_key)
    # Fernet uses random IV, so ciphertexts differ
    assert e1 != e2


def test_decrypt_with_wrong_key_raises():
    import pytest
    encrypted = encrypt_value("secret", "key-one-for-fernet-testing-32!!")
    with pytest.raises(Exception):
        decrypt_value(encrypted, "key-two-for-fernet-testing-32!!")


def test_encrypt_empty_string():
    secret_key = "test-secret-key-for-fernet-32!!"
    encrypted = encrypt_value("", secret_key)
    assert decrypt_value(encrypted, secret_key) == ""
