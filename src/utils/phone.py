import re

def normalize_phone(phone: str) -> str:
    """
    Normalizes Ethiopian phone numbers to 9-digit format (strips leading 0).
    Input can be '0912345678', '912345678', '+251912345678'.
    Output will be '912345678'.
    """
    if not phone:
        return phone
    
    # Remove all non-digits
    phone = re.sub(r"\D", "", phone)
    
    # Handle +251 or 251 prefix
    if phone.startswith("251") and len(phone) > 9:
        phone = phone[3:]
    
    # Handle leading 0
    if phone.startswith("0"):
        phone = phone[1:]
        
    return phone

def validate_ethiopian_phone(phone: str) -> bool:
    """
    Validates Ethiopian phone numbers.
    Accepts 9 digits starting with 9 or 7,
    OR 10 digits starting with 09 or 07.
    """
    if not phone:
        return False
    
    # Normalize first to check core digits
    normalized = normalize_phone(phone)
    pattern = r"^[97]\d{8}$"
    return bool(re.match(pattern, normalized))
