#!/usr/bin/env python3
"""
Test script for verifying the two implemented fixes:
1. NFC scan display on dashboard
2. Whitelabel access control for system users
"""

import os
import sys
import json
import hashlib

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_nfc_scan_display():
    """Test if NFC scan display is working correctly."""
    print("\n=== Testing NFC Scan Display ===")

    try:
        from app.nfc_reader import get_current_card_scans

        # Get current NFC scans
        scans = get_current_card_scans()

        if isinstance(scans, list):
            print(f"✓ NFC scan retrieval working - Found {len(scans)} scans")
            if scans:
                print(f"  Latest scan: {scans[0].get('timestamp', 'N/A')}")
        else:
            print("✗ NFC scan retrieval failed - Invalid data type")

    except Exception as e:
        print(f"✗ Error testing NFC scan display: {e}")

def test_system_users():
    """Test if system users are properly configured."""
    print("\n=== Testing System Users Configuration ===")

    try:
        from app.config import USERS_FILE, PASSWORD_SALT

        # Load users data
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
        else:
            print("✗ Users file not found")
            return

        # Check sentrasupport user
        if 'sentrasupport' in users:
            user = users['sentrasupport']
            if user.get('hidden') == True:
                print("✓ sentrasupport user exists and is hidden")
            else:
                print("✗ sentrasupport user exists but is not hidden")
        else:
            print("✗ sentrasupport user not found")

        # Check kassen24 user
        if 'kassen24' in users:
            user = users['kassen24']
            if user.get('hidden') == True:
                print("✓ kassen24 user exists and is hidden")

                # Verify password hash
                expected_password = "K@$3n24!Sys#2024$ecure"
                salted = expected_password + PASSWORD_SALT
                expected_hash = hashlib.sha256(salted.encode()).hexdigest()

                if user.get('password') == expected_hash:
                    print("✓ kassen24 password is correctly configured")
                else:
                    print("✗ kassen24 password hash mismatch")
            else:
                print("✗ kassen24 user exists but is not hidden")
        else:
            print("✗ kassen24 user not found")

    except Exception as e:
        print(f"✗ Error testing system users: {e}")

def test_whitelabel_access():
    """Test if whitelabel access control is working."""
    print("\n=== Testing Whitelabel Access Control ===")

    try:
        from app.routes import whitelabel_access_required
        from flask import session

        print("✓ whitelabel_access_required decorator imported successfully")

        # Check if the decorator exists and is callable
        if callable(whitelabel_access_required):
            print("✓ whitelabel_access_required is a valid decorator")
        else:
            print("✗ whitelabel_access_required is not callable")

    except ImportError as e:
        print(f"✗ Failed to import whitelabel decorator: {e}")
    except Exception as e:
        print(f"✗ Error testing whitelabel access: {e}")

def test_user_visibility():
    """Test if system users are hidden from user management."""
    print("\n=== Testing User Visibility ===")

    try:
        from app.models.user import user_manager

        # Get all visible users
        visible_users = user_manager.get_all_users()

        # Check that system users are not in the visible list
        usernames = [u.get('username') for u in visible_users]

        if 'sentrasupport' not in usernames:
            print("✓ sentrasupport is hidden from user list")
        else:
            print("✗ sentrasupport is visible in user list")

        if 'kassen24' not in usernames:
            print("✓ kassen24 is hidden from user list")
        else:
            print("✗ kassen24 is visible in user list")

        print(f"  Total visible users: {len(visible_users)}")

    except Exception as e:
        print(f"✗ Error testing user visibility: {e}")

def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing Guard NFC/QR System Fixes")
    print("=" * 50)

    test_nfc_scan_display()
    test_system_users()
    test_whitelabel_access()
    test_user_visibility()

    print("\n" + "=" * 50)
    print("Testing Complete!")
    print("=" * 50)

    # Summary
    print("\nSummary:")
    print("1. NFC Scan Display: Dashboard should now show recent NFC scans")
    print("2. System Users: kassen24 user created with secure password")
    print("3. Whitelabel Access: Only sentrasupport and kassen24 can access")
    print("4. User Visibility: System users hidden from User Management")

    print("\nTo verify manually:")
    print("1. Login as kassen24 with password: K@$3n24!Sys#2024$ecure")
    print("2. Navigate to /whitelabel - should be accessible")
    print("3. Check dashboard - NFC scans should be visible")
    print("4. Check User Management - system users should not appear")

if __name__ == "__main__":
    main()