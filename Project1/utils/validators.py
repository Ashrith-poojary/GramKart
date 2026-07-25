import re
from email_validator import validate_email, EmailNotValidError

def validate_phone_number(phone):
    """Validate standard Indian 10-digit phone format."""
    if not phone:
        return False
    # Matches exactly 10 digits
    return bool(re.match(r'^[6-9]\d{9}$', str(phone).strip()))

def validate_user_email(email):
    """Verify email formatting structure using email_validator."""
    if not email:
        return False
    try:
        validate_email(email.strip(), check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

def validate_password_complexity(password):
    """Enforce basic security password rules: min 4 chars."""
    if not password:
        return False
    return len(password) >= 4

def sanitize_string(val):
    """Sanitize inputs by removing leading/trailing whitespace and html-like brackets."""
    if not val:
        return ""
    cleaned = str(val).strip()
    cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
    return cleaned
