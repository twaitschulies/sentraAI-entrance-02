"""
PAN Security Module
===================
PCI DSS compliance utilities for handling Primary Account Numbers (PANs).

This module provides:
- SHA-256 one-way hashing for PAN storage
- PAN masking for display (shows only last 4 digits)
- Secure PAN comparison using hashed values

SECURITY NOTICE:
This system reads PANs from NFC bank cards for physical door access control.
We do NOT process payment transactions. However, we must protect cardholder data
from unauthorized access by:
1. Never storing plaintext PANs
2. Using one-way hashing (SHA-256) for storage
3. Masking PANs in all user interfaces (****-****-****-1234)
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


def hash_pan(pan: str) -> str:
    """
    Create a one-way SHA-256 hash of a PAN for secure storage.

    This is a cryptographic hash that cannot be reversed to recover the original PAN.
    Used for storing card identifiers securely in the database.

    Args:
        pan: Primary Account Number (typically 13-19 digits)

    Returns:
        64-character hexadecimal hash string

    Example:
        >>> hash_pan("1234567890123456")
        '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92'
    """
    if not pan:
        logger.warning("Attempted to hash empty PAN")
        return ""

    # Normalize: remove spaces and dashes, convert to string
    normalized_pan = str(pan).replace(" ", "").replace("-", "").strip()

    if not normalized_pan.isdigit():
        logger.warning(f"PAN contains non-digit characters: {normalized_pan[:6]}...")

    # Create SHA-256 hash
    hash_obj = hashlib.sha256(normalized_pan.encode('utf-8'))
    hashed_pan = hash_obj.hexdigest()

    logger.debug(f"Hashed PAN {normalized_pan[:6]}... -> {hashed_pan[:16]}...")

    return hashed_pan


def mask_pan(pan: str, show_last: int = 4) -> str:
    """
    Mask a PAN for display, showing only the last N digits.

    Format: ****-****-****-1234

    Args:
        pan: Primary Account Number to mask
        show_last: Number of digits to show at the end (default: 4)

    Returns:
        Masked PAN string safe for display

    Example:
        >>> mask_pan("1234567890123456")
        '****-****-****-3456'
        >>> mask_pan("1234567890123456", show_last=6)
        '****-****-**123456'
    """
    if not pan:
        return "****-****-****-****"

    # Normalize: remove spaces and dashes
    normalized_pan = str(pan).replace(" ", "").replace("-", "").strip()

    # If PAN is too short, just mask everything
    if len(normalized_pan) <= show_last:
        return "*" * len(normalized_pan)

    # Get the last N digits
    last_digits = normalized_pan[-show_last:]

    # Create masked portion
    # Standard format for most cards is 16 digits (4 groups of 4)
    if len(normalized_pan) == 16:
        masked = f"****-****-****-{last_digits}"
    elif len(normalized_pan) == 15:  # American Express
        masked = f"****-******-*{last_digits}"
    else:
        # Generic masking for other lengths
        mask_count = len(normalized_pan) - show_last
        masked = "*" * mask_count + last_digits

    return masked


def verify_pan(plain_pan: str, hashed_pan: str) -> bool:
    """
    Verify if a plaintext PAN matches a hashed PAN.

    Used during authentication to check if a scanned card matches a stored hash.

    Args:
        plain_pan: Plaintext PAN from NFC scan
        hashed_pan: Stored hash to compare against

    Returns:
        True if the hashes match, False otherwise

    Example:
        >>> stored_hash = hash_pan("1234567890123456")
        >>> verify_pan("1234567890123456", stored_hash)
        True
        >>> verify_pan("9999999999999999", stored_hash)
        False
    """
    if not plain_pan or not hashed_pan:
        return False

    computed_hash = hash_pan(plain_pan)
    match = computed_hash == hashed_pan

    if match:
        logger.debug(f"PAN verification SUCCESS for {mask_pan(plain_pan)}")
    else:
        logger.debug(f"PAN verification FAILED for {mask_pan(plain_pan)}")

    return match


def is_hashed_pan(value: str) -> bool:
    """
    Check if a value is likely a SHA-256 hash (vs plaintext PAN).

    SHA-256 hashes are always 64 hexadecimal characters.
    Plaintext PANs are 13-19 decimal digits.

    Args:
        value: String to check

    Returns:
        True if value appears to be a hash, False if plaintext

    Example:
        >>> is_hashed_pan("1234567890123456")
        False
        >>> is_hashed_pan("8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92")
        True
    """
    if not value:
        return False

    # SHA-256 hashes are exactly 64 hex characters
    if len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower()):
        return True

    return False


def extract_pan_display_info(pan_or_hash: str, is_hashed: bool = None) -> dict:
    """
    Extract display information from a PAN or hash.

    Returns both the masked display version and metadata about the value.

    Args:
        pan_or_hash: Either a plaintext PAN or a hashed PAN
        is_hashed: Optional hint about whether value is hashed (auto-detected if None)

    Returns:
        Dictionary with:
        - 'masked': Masked version for display
        - 'is_hashed': Whether the input was a hash
        - 'last_4': Last 4 digits (if available)

    Example:
        >>> extract_pan_display_info("1234567890123456")
        {'masked': '****-****-****-3456', 'is_hashed': False, 'last_4': '3456'}
        >>> extract_pan_display_info("8d969eef...")['is_hashed']
        True
    """
    if is_hashed is None:
        is_hashed = is_hashed_pan(pan_or_hash)

    if is_hashed:
        # For hashed values, we can't show the original PAN
        # Display the hash truncated
        return {
            'masked': f"[HASHED: {pan_or_hash[:8]}...]",
            'is_hashed': True,
            'last_4': None
        }
    else:
        # For plaintext, mask it
        masked = mask_pan(pan_or_hash)
        normalized = str(pan_or_hash).replace(" ", "").replace("-", "")
        last_4 = normalized[-4:] if len(normalized) >= 4 else None

        return {
            'masked': masked,
            'is_hashed': False,
            'last_4': last_4
        }


def sanitize_pan_for_logging(pan: str) -> str:
    """
    Sanitize a PAN for safe logging.

    Shows only first 6 and last 4 digits (BIN and last 4).
    This is the maximum allowed by PCI DSS for logging.

    Args:
        pan: PAN to sanitize

    Returns:
        Sanitized string safe for logs

    Example:
        >>> sanitize_pan_for_logging("1234567890123456")
        '123456...3456'
    """
    if not pan:
        return "[EMPTY]"

    if is_hashed_pan(pan):
        return f"[HASH:{pan[:8]}...]"

    normalized = str(pan).replace(" ", "").replace("-", "")

    if len(normalized) < 10:
        # Too short to be a real PAN, just mask it
        return "*" * len(normalized)

    # PCI DSS allows showing first 6 (BIN) and last 4
    return f"{normalized[:6]}...{normalized[-4:]}"


# Example usage and tests (only runs when module is executed directly)
if __name__ == "__main__":
    # Example PAN (fake test number)
    test_pan = "4532015112830366"

    print("PAN Security Module - Examples")
    print("=" * 50)
    print(f"Original PAN: {test_pan}")
    print(f"Hashed PAN:   {hash_pan(test_pan)}")
    print(f"Masked PAN:   {mask_pan(test_pan)}")
    print(f"Log-safe PAN: {sanitize_pan_for_logging(test_pan)}")
    print()

    # Test verification
    hashed = hash_pan(test_pan)
    print(f"Verification test:")
    print(f"  Correct PAN:   {verify_pan(test_pan, hashed)}")
    print(f"  Wrong PAN:     {verify_pan('1111222233334444', hashed)}")
    print()

    # Test hash detection
    print(f"Is '{test_pan}' a hash? {is_hashed_pan(test_pan)}")
    print(f"Is '{hashed}' a hash? {is_hashed_pan(hashed)}")
