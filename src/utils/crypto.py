from src.config import settings
import base64
import hashlib
import hmac
from cryptography.fernet import Fernet

# Derive a 32-byte key from the SECRET_KEY for AES-256
def _get_fernet() -> Fernet:
    # We need exactly 32 bytes for Fernet key
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)

def encrypt_data(data: str) -> str:
    """Encrypts a string using AES-256 (Fernet) - Non-deterministic"""
    if not data:
        return data
    f = _get_fernet()
    return f.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypts an AES-256 encrypted string"""
    if not encrypted_data:
        return encrypted_data
    f = _get_fernet()
    try:
        return f.decrypt(encrypted_data.encode()).decode()
    except Exception:
        # Fallback for old XOR data or failed decryption
        return encrypted_data

def hash_data(data: str) -> str:
    """Creates a deterministic HMAC-SHA256 hash for database lookups"""
    if not data:
        return data
    return hmac.new(
        settings.SECRET_KEY.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()

# Aliases for backward compatibility
def encrypt_phone(phone: str) -> str:
    return encrypt_data(phone)

def decrypt_phone(encrypted_phone: str) -> str:
    return decrypt_data(encrypted_phone)

def hash_phone(phone: str) -> str:
    return hash_data(phone)
