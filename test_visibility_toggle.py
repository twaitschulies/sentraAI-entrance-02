#!/usr/bin/env python3
"""
Interactive test script to demonstrate barcode visibility toggle behavior.
This script allows you to toggle the barcode_visibility_enabled setting
and see what changes should be visible in the UI.
"""

import json
import os
from pathlib import Path

CONFIG_FILE = Path("config.json")

def load_config():
    """Load current configuration"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            return config if config else {}
    return {}

def save_config(config):
    """Save configuration"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ Configuration saved to {CONFIG_FILE}")

def toggle_barcode_visibility():
    """Toggle the barcode visibility setting"""
    config = load_config()
    current_state = config.get('barcode_visibility_enabled', True)
    new_state = not current_state

    config['barcode_visibility_enabled'] = new_state
    save_config(config)

    print("\n" + "=" * 60)
    print(f"🔄 Barcode Visibility TOGGLED")
    print(f"   Previous state: {current_state}")
    print(f"   New state: {new_state}")
    print("=" * 60)

    return new_state

def show_expected_ui_changes(enabled):
    """Display what should be visible/hidden based on the setting"""
    print("\n📱 EXPECTED UI CHANGES:")
    print("-" * 40)

    if enabled:
        print("✅ BARCODE FEATURES ENABLED")
        print("\nDashboard Page:")
        print("  • ✓ Barcode scans column VISIBLE (col-md-6)")
        print("  • ✓ NFC scans column at HALF width (col-md-6)")
        print("\nSettings Page:")
        print("  • ✓ 'Allow All Barcodes' option VISIBLE")
        print("\nNavigation Menu:")
        print("  • ✓ 'Barcodes' menu item VISIBLE")
        print("\nAPI Endpoints:")
        print("  • ✓ Barcode scanning endpoints ACTIVE")
    else:
        print("❌ BARCODE FEATURES DISABLED")
        print("\nDashboard Page:")
        print("  • ✗ Barcode scans column HIDDEN")
        print("  • ✓ NFC scans column at FULL width (col-md-12)")
        print("\nSettings Page:")
        print("  • ✗ 'Allow All Barcodes' option HIDDEN")
        print("\nNavigation Menu:")
        print("  • ✗ 'Barcodes' menu item HIDDEN")
        print("\nAPI Endpoints:")
        print("  • ✗ Barcode scanning endpoints BLOCKED")

def main():
    print("=" * 60)
    print("🧪 BARCODE VISIBILITY TOGGLE TEST")
    print("=" * 60)

    # Check current state
    config = load_config()
    current_state = config.get('barcode_visibility_enabled', True)

    print(f"\n📊 Current State: barcode_visibility_enabled = {current_state}")

    while True:
        print("\n" + "-" * 40)
        print("OPTIONS:")
        print("  1. Toggle barcode visibility")
        print("  2. Show current UI state")
        print("  3. Exit")
        print("-" * 40)

        choice = input("\nEnter choice (1-3): ").strip()

        if choice == '1':
            new_state = toggle_barcode_visibility()
            show_expected_ui_changes(new_state)
            print("\n⚠️  IMPORTANT: Restart the application or refresh the page")
            print("   to see the changes take effect!")

        elif choice == '2':
            config = load_config()
            current_state = config.get('barcode_visibility_enabled', True)
            print(f"\n📊 Current: barcode_visibility_enabled = {current_state}")
            show_expected_ui_changes(current_state)

        elif choice == '3':
            print("\n👋 Exiting...")
            break
        else:
            print("\n❌ Invalid choice. Please enter 1, 2, or 3.")

    print("\n" + "=" * 60)
    print("🔍 MANUAL VERIFICATION STEPS:")
    print("1. Login as 'sentrasupport' user")
    print("2. Check Settings > Door Settings")
    print("3. Verify 'Barcode-Funktionalität aktiviert' matches config")
    print("4. Navigate to Dashboard")
    print("5. Verify barcode column visibility matches setting")
    print("=" * 60)

if __name__ == "__main__":
    main()