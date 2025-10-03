#!/usr/bin/env python3
"""
Test script to verify the UI bug fixes:
1. Menu toggle functionality
2. Dashboard barcode timestamp visibility

Usage: python3 test_ui_fixes.py
"""

import json
import os

# Path to config file
CONFIG_FILE = "config.json"

def test_barcode_visibility_setting():
    """Test if barcode visibility setting is properly configured"""
    print("=" * 60)
    print("Testing Barcode Visibility Setting")
    print("=" * 60)

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            barcode_visibility = config.get('barcode_visibility_enabled', True)
            print(f"✓ Config file exists")
            print(f"  - barcode_visibility_enabled: {barcode_visibility}")

            if not barcode_visibility:
                print(f"  ✓ Barcode features are DISABLED")
                print(f"    - Dashboard should NOT show barcode timestamps")
                print(f"    - Historical barcode scans section should be HIDDEN")
                print(f"    - Barcode menu item should be HIDDEN")
            else:
                print(f"  ✓ Barcode features are ENABLED")
                print(f"    - Dashboard will show barcode timestamps")
                print(f"    - Historical barcode scans section will be VISIBLE")
                print(f"    - Barcode menu item will be VISIBLE")
    else:
        print(f"⚠ Config file not found at {CONFIG_FILE}")
        print(f"  - System will use default: barcode_visibility_enabled = True")

    print()

def test_menu_toggle_fix():
    """Verify menu toggle JavaScript fix"""
    print("=" * 60)
    print("Testing Menu Toggle Fix")
    print("=" * 60)

    kaiadmin_path = "app/static/js/kaiadmin.js"
    if os.path.exists(kaiadmin_path):
        with open(kaiadmin_path, 'r') as f:
            content = f.read()

            # Check if the conflicting code has been removed
            if "localStorage.setItem('sidebar-collapsed'" not in content:
                print(f"✓ kaiadmin.js has been fixed")
                print(f"  - Removed conflicting localStorage code")
                print(f"  - Menu toggle should work via session storage")
            else:
                print(f"⚠ kaiadmin.js still has conflicting code")
                print(f"  - Menu toggle might have issues")

            if "data-listener-attached" in content:
                print(f"✓ Duplicate listener prevention added")
    else:
        print(f"⚠ kaiadmin.js not found at {kaiadmin_path}")

    print()

def test_dashboard_template():
    """Verify dashboard template changes"""
    print("=" * 60)
    print("Testing Dashboard Template Changes")
    print("=" * 60)

    dashboard_path = "app/templates/dashboard.html"
    if os.path.exists(dashboard_path):
        with open(dashboard_path, 'r') as f:
            content = f.read()

            # Check if conditional rendering is in place
            if "{% if barcode_visibility_enabled %}" in content and "historical-scans-section" in content:
                print(f"✓ Dashboard template has been updated")
                print(f"  - Historical scans section is conditionally rendered")
                print(f"  - Will be hidden when barcode features are disabled")
            else:
                print(f"⚠ Dashboard template might not be properly updated")

            if "Historische Barcode-Scans" in content:
                print(f"✓ Section title clarified as 'Barcode-Scans'")
    else:
        print(f"⚠ Dashboard template not found at {dashboard_path}")

    print()

def test_routes_update():
    """Verify routes.py changes"""
    print("=" * 60)
    print("Testing Routes Backend Changes")
    print("=" * 60)

    routes_path = "app/routes.py"
    if os.path.exists(routes_path):
        with open(routes_path, 'r') as f:
            content = f.read()

            # Check if barcode filtering is in place
            if "barcode_visibility_enabled = settings.get('barcode_visibility_enabled'," in content:
                print(f"✓ Routes.py has been updated")
                print(f"  - Dashboard route checks barcode_visibility_enabled")
                print(f"  - Barcode scans excluded when feature is disabled")
            else:
                print(f"⚠ Routes.py might not be properly updated")
    else:
        print(f"⚠ Routes.py not found at {routes_path}")

    print()

def main():
    print("\n" + "=" * 60)
    print("UI BUG FIXES TEST REPORT")
    print("=" * 60 + "\n")

    test_barcode_visibility_setting()
    test_menu_toggle_fix()
    test_dashboard_template()
    test_routes_update()

    print("=" * 60)
    print("TESTING COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start the application: python3 wsgi.py")
    print("2. Test menu toggle by clicking the hamburger icon")
    print("3. Log in as sentrasupport to toggle barcode visibility")
    print("4. Check dashboard with barcode features on/off")
    print("\nNote: To disable barcode features as sentrasupport:")
    print("  - Go to Settings > Door Settings")
    print("  - Uncheck 'Barcode-Funktionalität aktiviert'")
    print("  - Save settings")

if __name__ == "__main__":
    main()