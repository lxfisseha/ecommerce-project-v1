from src.config import settings
import base64
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)
from cryptography.fernet import Fernet, InvalidToken


def derive_key(purpose: str) -> str:
    """Derive a purpose-specific key from SECRET_KEY using domain separation.
    
    Each purpose (e.g. 'session', 'csrf', 'encryption', 'hmac') produces a
    cryptographically independent key, so compromising one does not affect others.
    Returns a base64-encoded string suitable as a secret/key for middlewares.
    """
    raw = hmac.new(
        settings.SECRET_KEY.encode(),
        purpose.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(raw).decode()


def _get_fernet() -> Fernet:
    return Fernet(derive_key("encryption"))

def _get_legacy_fernet() -> Fernet:
    """Legacy Fernet key derivation using raw SHA256 of SECRET_KEY (pre-derive_key)"""
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


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
    except InvalidToken:
        # Data encrypted with old key — try legacy fallback
        try:
            return legacy_decrypt_data(encrypted_data)
        except Exception:
            logger.error("Legacy decryption also failed for data")
            return "[encrypted]"
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return "[encrypted]" 

def legacy_decrypt_data(encrypted_data: str) -> str:
    """Decrypts data encrypted with the legacy Fernet key (SHA256 of SECRET_KEY)"""
    if not encrypted_data:
        return encrypted_data
    f = _get_legacy_fernet()
    return f.decrypt(encrypted_data.encode()).decode()

def hash_data(data: str) -> str:
    """Creates a deterministic HMAC-SHA256 hash for database lookups (current)"""
    if not data:
        return data
    return hmac.new(
        derive_key("hmac").encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()

def legacy_hash_data(data: str) -> str:
    """Legacy HMAC-SHA256 hash using raw SECRET_KEY (pre-derive_key)"""
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

def legacy_hash_phone(phone: str) -> str:
    return legacy_hash_data(phone)

def legacy_decrypt_phone(encrypted_phone: str) -> str:
    return legacy_decrypt_data(encrypted_phone)
