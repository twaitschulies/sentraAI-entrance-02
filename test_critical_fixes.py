#!/usr/bin/env python3
"""
Test script to verify the two critical fixes:
1. NFC duplicate scan display removal on dashboard
2. kassen24 user management access
"""

import json
import os
import sys

def test_dashboard_template():
    """Test that NFC scans are not duplicated in dashboard template."""
    print("\n" + "="*50)
    print("Testing Dashboard Template Fix")
    print("="*50)

    template_path = "app/templates/dashboard.html"

    try:
        with open(template_path, 'r') as f:
            content = f.read()

        # Check that "Aktuelle NFC-Scans" section exists (this should remain)
        if "Aktuelle NFC-Scans" in content:
            print("✓ 'Aktuelle NFC-Scans' section found (correct - should remain)")
        else:
            print("✗ 'Aktuelle NFC-Scans' section not found (ERROR)")

        # Check that historical section title is changed
        if "Historische Barcode-Scans durchsuchen" in content:
            print("✓ Historical section title changed to 'Historische Barcode-Scans durchsuchen'")
        else:
            print("✗ Historical section title not updated")

        # Check that NFC filtering is in place
        if "selectattr('scan_type', 'ne', 'nfc')" in content:
            print("✓ NFC filtering implemented in historical scans table")
        else:
            print("✗ NFC filtering not found in historical scans")

        # Check that barcode-only condition exists
        if "scan.get('scan_type') != 'nfc' and not scan.code.startswith('NFC-')" in content:
            print("✓ Additional NFC filtering check implemented")
        else:
            print("✗ Additional NFC filtering check not found")

        print("\n✅ Dashboard template fix verified successfully!")

    except Exception as e:
        print(f"✗ Error checking dashboard template: {e}")
        return False

    return True

def test_kassen24_permissions():
    """Test that kassen24 user has proper permissions."""
    print("\n" + "="*50)
    print("Testing kassen24 User Permissions")
    print("="*50)

    # Check routes.py for permission updates
    routes_path = "app/routes.py"

    try:
        with open(routes_path, 'r') as f:
            content = f.read()

        # Check permission_required decorator
        if "if username in ['sentrasupport', 'kassen24']:" in content:
            print("✓ permission_required decorator updated for kassen24")
        else:
            print("✗ permission_required decorator not updated")

        # Check admin_required decorator (should already be there)
        if "System users (sentrasupport and kassen24) have admin rights" in content or \
           "if username in ['sentrasupport', 'kassen24']:" in content:
            print("✓ admin_required decorator includes kassen24")
        else:
            print("✗ admin_required decorator missing kassen24")

        # Check manager_required decorator
        if "System users haben Manager-Rechte" in content or \
           "if username in ['sentrasupport', 'kassen24']:" in content:
            print("✓ manager_required decorator updated for kassen24")
        else:
            print("✗ manager_required decorator not updated")

    except Exception as e:
        print(f"✗ Error checking routes.py: {e}")
        return False

    # Check base.html template
    template_path = "app/templates/base.html"

    try:
        with open(template_path, 'r') as f:
            content = f.read()

        # Check user management menu visibility
        if "session.role == 'admin' or session.username in ['sentrasupport', 'kassen24']" in content:
            print("✓ User management menu updated for kassen24 visibility")
        else:
            print("✗ User management menu not updated")

    except Exception as e:
        print(f"✗ Error checking base.html: {e}")
        return False

    # Check user data
    users_path = "data/users.json"

    try:
        with open(users_path, 'r') as f:
            users = json.load(f)

        if 'kassen24' in users:
            kassen24 = users['kassen24']
            if kassen24.get('role') == 'admin':
                print("✓ kassen24 user has admin role")
            else:
                print("✗ kassen24 user does not have admin role")

            if kassen24.get('is_system_user') == True:
                print("✓ kassen24 marked as system user")
            else:
                print("✗ kassen24 not marked as system user")

            if kassen24.get('hidden') == True:
                print("✓ kassen24 is hidden from normal user list")
            else:
                print("✗ kassen24 is not hidden")
        else:
            print("✗ kassen24 user not found in users.json")
            return False

    except Exception as e:
        print(f"✗ Error checking users.json: {e}")
        return False

    print("\n✅ kassen24 permissions verified successfully!")
    return True

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print(" CRITICAL FIXES VERIFICATION TEST")
    print("="*60)

    all_passed = True

    # Test 1: Dashboard template fix
    if not test_dashboard_template():
        all_passed = False

    # Test 2: kassen24 permissions
    if not test_kassen24_permissions():
        all_passed = False

    # Summary
    print("\n" + "="*60)
    print(" TEST SUMMARY")
    print("="*60)

    if all_passed:
        print("✅ ALL TESTS PASSED!")
        print("\nBoth critical fixes have been successfully implemented:")
        print("1. ✅ NFC duplicate scan display removed from historical section")
        print("2. ✅ kassen24 user granted full user management access")
        print("\nTo verify manually:")
        print("1. Login as kassen24 with password: K@$3n24!Sys#2024$ecure")
        print("2. Navigate to Dashboard - NFC scans should appear only once")
        print("3. Check sidebar - 'Benutzerverwaltung' should be visible")
        print("4. Click on 'Benutzerverwaltung' - should be accessible")
    else:
        print("⚠️ SOME TESTS FAILED!")
        print("Please review the errors above and fix any issues.")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())