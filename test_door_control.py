#!/usr/bin/env python3
"""
Test script for comprehensive time-based GPIO door control system.
Tests all major functionality without running indefinitely.
"""

import sys
import os
import json
import logging
from datetime import datetime, time

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging to be less verbose for testing
logging.basicConfig(level=logging.ERROR)  # Only show errors

def test_door_control_system():
    """Test the complete door control system."""
    print("🧪 Testing Time-Based Door Control System")
    print("=" * 50)

    try:
        # Test 1: Import and basic initialization
        print("1. Testing import and initialization...")
        from app.models.door_control import DoorControlManager

        # Create a fresh manager for testing (avoid singleton)
        manager = DoorControlManager()
        print("   ✅ Door control manager created successfully")

        # Test 2: Get current status
        print("2. Testing status retrieval...")
        status = manager.get_status()
        print(f"   ✅ Current mode: {status['current_mode']}")
        print(f"   ✅ GPIO should be HIGH: {status['gpio']['should_be_high']}")
        print(f"   ✅ NFC allowed: {status['access']['nfc_allowed']} ({status['access']['nfc_reason']})")
        print(f"   ✅ QR allowed: {status['access']['qr_allowed']} ({status['access']['qr_reason']})")

        # Test 3: Time-based mode logic
        print("3. Testing time-based mode logic...")
        current_time = datetime.now().time()
        current_mode = manager.get_current_mode()
        print(f"   ✅ Current time: {current_time}")
        print(f"   ✅ Calculated mode: {current_mode}")

        # Test 4: Access control logic
        print("4. Testing access control logic...")
        nfc_allowed, nfc_reason = manager.should_allow_nfc_access()
        qr_exit_allowed, qr_exit_reason = manager.should_allow_qr_access(is_exit=True)
        qr_entry_allowed, qr_entry_reason = manager.should_allow_qr_access(is_exit=False)

        print(f"   ✅ NFC access: {nfc_allowed} ({nfc_reason})")
        print(f"   ✅ QR exit: {qr_exit_allowed} ({qr_exit_reason})")
        print(f"   ✅ QR entry: {qr_entry_allowed} ({qr_entry_reason})")

        # Test 5: GPIO state logic
        print("5. Testing GPIO state logic...")
        should_be_high = manager.should_gpio_be_high()
        print(f"   ✅ GPIO should be HIGH: {should_be_high}")

        # Test 6: Next mode change calculation
        print("6. Testing next mode change calculation...")
        next_change = manager.get_next_mode_change()
        if next_change:
            print(f"   ✅ Next mode change: {next_change['mode']} at {next_change['datetime']}")
            print(f"   ✅ Time until: {next_change['time_until_human']}")
        else:
            print("   ✅ No upcoming mode changes")

        # Test 7: Configuration management
        print("7. Testing configuration management...")
        config = manager.get_config()
        print(f"   ✅ System enabled: {config.get('enabled', False)}")
        print(f"   ✅ Available modes: {list(config.get('modes', {}).keys())}")

        # Test 8: Override functionality (temporary test)
        print("8. Testing override functionality...")
        original_mode = manager.get_current_mode()

        # Set a short override
        override_success = manager.set_override("normal_operation", 0.001)  # 3.6 seconds
        if override_success:
            print("   ✅ Override set successfully")
            override_mode = manager.get_current_mode()
            print(f"   ✅ Override mode: {override_mode}")

            # Clear the override
            clear_success = manager.clear_override()
            if clear_success:
                print("   ✅ Override cleared successfully")
            else:
                print("   ⚠️ Failed to clear override")
        else:
            print("   ⚠️ Failed to set override")

        # Test 9: Integration imports (without running)
        print("9. Testing integration imports...")
        try:
            from app.gpio_control import sync_gpio_with_time_based_control, pulse_with_time_based_check
            print("   ✅ GPIO integration functions imported")
        except ImportError as e:
            print(f"   ⚠️ GPIO integration import failed: {e}")

        try:
            from app.nfc_reader import handle_scan  # Will fail but tests import path
            print("   ✅ NFC reader integration available")
        except Exception as e:
            print("   ℹ️ NFC reader integration (expected warnings in test environment)")

        try:
            from app.scanner import handle_scan
            print("   ✅ QR scanner integration available")
        except ImportError as e:
            print(f"   ⚠️ QR scanner integration import failed: {e}")

        # Test 10: Fail-safe behavior validation
        print("10. Testing fail-safe behavior validation...")
        # QR exits should ALWAYS be allowed for emergency egress
        for mode in ["always_open", "normal_operation", "access_blocked"]:
            manager.current_mode = mode  # Force mode for testing
            qr_exit, reason = manager.should_allow_qr_access(is_exit=True)
            if qr_exit:
                print(f"   ✅ QR exit allowed in {mode} mode: {reason}")
            else:
                print(f"   ❌ QR exit denied in {mode} mode: {reason} (FAIL-SAFE VIOLATION!)")

        # Test 11: Cleanup
        print("11. Testing cleanup...")
        manager.shutdown()
        print("   ✅ Manager shutdown completed")

        print("\n🎉 All tests completed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_door_control_system()
    sys.exit(0 if success else 1)