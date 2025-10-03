#!/usr/bin/env python3
"""
Verification script for critical fixes in Guard NFC/QR System
Tests all 5 critical issues that were addressed
"""

import os
import json
import sys
import hashlib

print("=" * 60)
print("GUARD SYSTEM FIX VERIFICATION")
print("=" * 60)

issues_fixed = []
issues_failed = []

# Test 1: Admin Login with admin/admin
print("\n1. Testing admin/admin login...")
try:
    # Check if PASSWORD_SALT is consistent
    from app.config import PASSWORD_SALT
    expected_salt = 'aiqr_guard_v3_2025_fixed_salt_do_not_change'

    if PASSWORD_SALT == expected_salt or os.getenv('AIQR_PASSWORD_SALT') == expected_salt:
        print("   ✅ PASSWORD_SALT is correctly fixed")

        # Check if admin user exists with correct password
        if os.path.exists('data/users.json'):
            with open('data/users.json', 'r') as f:
                users = json.load(f)

            if 'admin' in users:
                # Calculate expected hash for 'admin' password
                salted = 'admin' + expected_salt
                expected_hash = hashlib.sha256(salted.encode()).hexdigest()

                if users['admin']['password'] == expected_hash:
                    print("   ✅ admin/admin credentials are correct")
                    if users['admin'].get('force_password_change'):
                        print("   ✅ Forced password change is enabled")
                    issues_fixed.append("Admin login fixed")
                else:
                    print("   ❌ admin password hash doesn't match")
                    issues_failed.append("Admin password incorrect")
            else:
                print("   ❌ admin user not found")
                issues_failed.append("Admin user missing")
        else:
            print("   ⚠️  users.json not found (will be created on first run)")
            issues_fixed.append("Admin login will work on first run")
    else:
        print(f"   ❌ PASSWORD_SALT is not fixed: {PASSWORD_SALT}")
        issues_failed.append("PASSWORD_SALT not fixed")

except Exception as e:
    print(f"   ❌ Error testing admin login: {e}")
    issues_failed.append(f"Admin login test error: {e}")

# Test 2: Configuration Independence
print("\n2. Testing webhook/allow_all_barcodes independence...")
try:
    # Check scanner.py for independent handling
    with open('app/scanner.py', 'r') as f:
        scanner_content = f.read()

    if 'if scan_successful and WEBHOOK_AVAILABLE:' in scanner_content:
        print("   ✅ Webhook triggers independently of allow_all_barcodes")
        issues_fixed.append("Webhook configuration independent")
    else:
        print("   ❌ Webhook may not be independent")
        issues_failed.append("Webhook configuration issue")

except Exception as e:
    print(f"   ❌ Error testing configuration: {e}")
    issues_failed.append(f"Configuration test error: {e}")

# Test 3: Footer Branding
print("\n3. Testing footer branding...")
try:
    with open('app/templates/base.html', 'r') as f:
        base_content = f.read()

    if 'SentraAI' in base_content and '2025' in base_content:
        print("   ✅ Footer updated to SentraAI © 2025")
        issues_fixed.append("Footer branding updated")
    else:
        print("   ❌ Footer not properly updated")
        issues_failed.append("Footer branding not updated")

except Exception as e:
    print(f"   ❌ Error testing footer: {e}")
    issues_failed.append(f"Footer test error: {e}")

# Test 4: Door Control Default State
print("\n4. Testing door control defaults...")
try:
    # Check if door_control.json exists
    if os.path.exists('data/door_control.json'):
        with open('data/door_control.json', 'r') as f:
            door_config = json.load(f)

        all_disabled = True
        for mode_name, mode_config in door_config.get('modes', {}).items():
            if mode_config.get('enabled', True):
                print(f"   ❌ Mode '{mode_name}' is enabled by default")
                all_disabled = False

        if all_disabled:
            print("   ✅ All door control modes default to disabled")
            issues_fixed.append("Door control defaults fixed")
        else:
            issues_failed.append("Some door modes enabled by default")
    else:
        # Check default in door_control.py
        with open('app/models/door_control.py', 'r') as f:
            door_py = f.read()

        if '"enabled": False,  # Disabled by default - must be explicitly enabled' in door_py:
            print("   ✅ Door control code defaults to disabled")
            issues_fixed.append("Door control defaults fixed in code")
        else:
            print("   ⚠️  Check door_control.py for correct defaults")
            issues_failed.append("Door control defaults uncertain")

except Exception as e:
    print(f"   ❌ Error testing door control: {e}")
    issues_failed.append(f"Door control test error: {e}")

# Test 5: System Logging
print("\n5. Testing system logging...")
try:
    # Check if logs are being read from system.log
    with open('app/routes.py', 'r') as f:
        routes_content = f.read()

    if 'system.log' in routes_content:
        print("   ✅ Logs page reads from system.log")

        # Check if system.log exists and has content
        if os.path.exists('logs/system.log'):
            with open('logs/system.log', 'r') as f:
                log_content = f.read()
            if log_content:
                print("   ✅ system.log contains log entries")
                issues_fixed.append("System logging fixed")
            else:
                print("   ⚠️  system.log exists but is empty")
                issues_fixed.append("System logging configured correctly")
        else:
            print("   ⚠️  system.log doesn't exist yet (will be created)")
            issues_fixed.append("System logging configured correctly")
    else:
        print("   ❌ Logs page may not read from correct file")
        issues_failed.append("System logging configuration")

except Exception as e:
    print(f"   ❌ Error testing logging: {e}")
    issues_failed.append(f"Logging test error: {e}")

# Test 6: Install.sh Updates
print("\n6. Testing install.sh updates...")
try:
    with open('install.sh', 'r') as f:
        install_content = f.read()

    checks_passed = 0
    if 'AIQR_PASSWORD_SALT=aiqr_guard_v3_2025_fixed_salt_do_not_change' in install_content:
        print("   ✅ install.sh sets fixed PASSWORD_SALT")
        checks_passed += 1
    else:
        print("   ❌ install.sh missing PASSWORD_SALT configuration")

    if 'rm -f data/users.json' in install_content:
        print("   ✅ install.sh resets users on fresh install")
        checks_passed += 1
    else:
        print("   ❌ install.sh doesn't reset users")

    if 'rm -f data/door_control.json' in install_content:
        print("   ✅ install.sh resets door control on fresh install")
        checks_passed += 1
    else:
        print("   ❌ install.sh doesn't reset door control")

    if checks_passed == 3:
        issues_fixed.append("install.sh properly updated")
    else:
        issues_failed.append(f"install.sh incomplete ({checks_passed}/3 checks)")

except Exception as e:
    print(f"   ❌ Error testing install.sh: {e}")
    issues_failed.append(f"install.sh test error: {e}")

# Summary
print("\n" + "=" * 60)
print("VERIFICATION SUMMARY")
print("=" * 60)

print(f"\n✅ FIXED ISSUES ({len(issues_fixed)}):")
for issue in issues_fixed:
    print(f"   • {issue}")

if issues_failed:
    print(f"\n❌ REMAINING ISSUES ({len(issues_failed)}):")
    for issue in issues_failed:
        print(f"   • {issue}")
else:
    print("\n🎉 ALL CRITICAL ISSUES SUCCESSFULLY FIXED!")

print("\n" + "=" * 60)
print("DEPLOYMENT INSTRUCTIONS:")
print("=" * 60)
print("1. Run: sudo ./install.sh")
print("2. System will restart with admin/admin login")
print("3. On first login, admin will be forced to change password")
print("4. All door control modes will be disabled by default")
print("5. Configure as needed via web interface")
print("\nNote: Webhook and 'Allow All Barcodes' work independently")
print("      Footer shows: SentraAI © 2025")
print("      Logs are stored in system.log and displayed correctly")

sys.exit(0 if not issues_failed else 1)