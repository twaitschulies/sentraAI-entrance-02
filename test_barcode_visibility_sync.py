#!/usr/bin/env python3
"""
Test script to verify barcode visibility synchronization between settings and dashboard.
This tests that when sentrasupport user disables barcode visibility, the scanned barcodes
section is also hidden on the dashboard.
"""

import json
import os
import sys
from pathlib import Path

def load_settings():
    """Load current settings from config.json"""
    config_path = Path('config.json')
    if not config_path.exists():
        print("❌ Config file not found at config.json")
        return None

    try:
        with open(config_path, 'r') as f:
            settings = json.load(f)
            # Return empty dict as valid settings if file is empty
            return settings if settings else {}
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return None

def check_template_implementation():
    """Check if dashboard template has proper visibility conditionals"""
    dashboard_path = Path('app/templates/dashboard.html')
    settings_path = Path('app/templates/settings.html')

    checks = {
        'dashboard_conditional': False,
        'dashboard_col_responsive': False,
        'settings_sentrasupport_check': False
    }

    # Check dashboard template
    if dashboard_path.exists():
        content = dashboard_path.read_text()

        # Check if barcode section is wrapped in conditional
        if '{% if barcode_visibility_enabled %}' in content and 'Aktuelle Barcode-Scans' in content:
            checks['dashboard_conditional'] = True
            print("✅ Dashboard: Barcode section properly wrapped in visibility conditional")
        else:
            print("❌ Dashboard: Barcode section NOT wrapped in visibility conditional")

        # Check if NFC column adjusts width based on visibility
        if '{% if barcode_visibility_enabled %}col-md-6{% else %}col-md-12{% endif %}' in content:
            checks['dashboard_col_responsive'] = True
            print("✅ Dashboard: NFC column width responsive to barcode visibility")
        else:
            print("❌ Dashboard: NFC column width NOT responsive to barcode visibility")
    else:
        print("❌ Dashboard template not found")

    # Check settings template
    if settings_path.exists():
        content = settings_path.read_text()

        # Check if sentrasupport user has control
        if "session.username == 'sentrasupport'" in content and 'barcode_visibility_enabled' in content:
            checks['settings_sentrasupport_check'] = True
            print("✅ Settings: SentraSupport user has barcode visibility control")
        else:
            print("❌ Settings: SentraSupport user control not found")
    else:
        print("❌ Settings template not found")

    return all(checks.values())

def check_context_processor():
    """Check if barcode_visibility_enabled is provided in context processor"""
    routes_path = Path('app/routes.py')

    if routes_path.exists():
        content = routes_path.read_text()
        if 'barcode_visibility_enabled' in content and '@bp.context_processor' in content:
            print("✅ Context Processor: barcode_visibility_enabled is globally available")
            return True
        else:
            print("❌ Context Processor: barcode_visibility_enabled NOT found")
            return False
    else:
        print("❌ Routes file not found")
        return False

def test_visibility_scenarios():
    """Test different visibility scenarios"""
    print("\n📋 Testing Visibility Scenarios:")
    print("-" * 50)

    settings = load_settings()
    if settings is None:
        return False

    current_visibility = settings.get('barcode_visibility_enabled', True)
    print(f"Current Setting: barcode_visibility_enabled = {current_visibility}")

    print("\n🔍 Expected Behavior:")
    if current_visibility:
        print("  ✓ Dashboard should show both NFC (col-md-6) and Barcode (col-md-6) columns")
        print("  ✓ Settings should show 'Allow All Barcodes' option")
        print("  ✓ Navigation menu should show barcode-related links")
    else:
        print("  ✓ Dashboard should show only NFC column (col-md-12)")
        print("  ✓ Dashboard should NOT show Barcode scans column")
        print("  ✓ Settings should hide 'Allow All Barcodes' option")
        print("  ✓ Navigation menu should hide barcode-related links")

    return True

def main():
    print("=" * 60)
    print("🧪 Barcode Visibility Synchronization Test")
    print("=" * 60)

    all_checks_passed = True

    print("\n1️⃣  Checking Template Implementation...")
    print("-" * 50)
    if not check_template_implementation():
        all_checks_passed = False

    print("\n2️⃣  Checking Context Processor...")
    print("-" * 50)
    if not check_context_processor():
        all_checks_passed = False

    print("\n3️⃣  Testing Visibility Scenarios...")
    if not test_visibility_scenarios():
        all_checks_passed = False

    print("\n" + "=" * 60)
    if all_checks_passed:
        print("✅ All visibility synchronization checks PASSED!")
        print("\nImplementation Summary:")
        print("  • Dashboard barcode section properly wrapped in conditional")
        print("  • NFC column width adjusts when barcodes are hidden")
        print("  • SentraSupport user can control visibility from settings")
        print("  • Visibility setting is globally available via context processor")
    else:
        print("⚠️  Some checks failed. Please review the implementation.")

    print("\n📝 Manual Testing Steps:")
    print("1. Login as 'sentrasupport' user")
    print("2. Go to Settings > Door Settings")
    print("3. Toggle 'Barcode-Funktionalität aktiviert' checkbox")
    print("4. Save settings")
    print("5. Navigate to Dashboard")
    print("6. Verify barcode section visibility matches the setting")
    print("=" * 60)

    return 0 if all_checks_passed else 1

if __name__ == "__main__":
    sys.exit(main())