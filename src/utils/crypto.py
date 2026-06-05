from src.config import settings
import base64

# Simple XOR-based deterministic "encryption" for this specific project requirement
# Note: In production, consider using a proper format-preserving encryption (FPE) library.
def _xor_cipher(data: str) -> str:
    key = settings.SECRET_KEY
    return base64.urlsafe_b64encode(
        bytes([ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(data)])
    ).decode()

def encrypt_phone(phone: str) -> str:
    return _xor_cipher(phone)

def decrypt_phone(encrypted_phone: str) -> str:
    key = settings.SECRET_KEY
    data = base64.urlsafe_b64decode(encrypted_phone.encode())
    return "".join([chr(c ^ ord(key[i % len(key)])) for i, c in enumerate(data)])
