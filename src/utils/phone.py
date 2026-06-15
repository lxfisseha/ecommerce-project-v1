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
    Accepts:
    - 9 digits starting with 9 or 7 (e.g., 912345678)
    - 10 digits starting with 09 or 07 (e.g., 0912345678)
    - 12 digits starting with 2519 or 2517 (e.g., 251912345678)
    """
    if not phone:
        return False
    
    # Remove all non-digits
    digits = re.sub(r"\D", "", phone)
    
    # Pattern: 
    # ^[97]\d{8}$              -> 9 digits starting with 9 or 7
    # ^0[97]\d{8}$             -> 10 digits starting with 09 or 07
    # ^251[97]\d{8}$           -> 12 digits starting with 2519 or 2517
    pattern = r"^([97]\d{8}|0[97]\d{8}|251[97]\d{8})$"
    return bool(re.match(pattern, digits))
