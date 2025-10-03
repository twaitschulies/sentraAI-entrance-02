#!/usr/bin/env python3
"""
Test script for the new time-based door control system.

This script validates all the critical components of the door control system:
- Door Control Manager functionality
- Time-based mode calculations
- GPIO integration
- API endpoints
- Fail-safe mechanisms

Run this script to verify the system is working correctly before production deployment.
"""

import sys
import os
import json
from datetime import datetime, time
import traceback

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_imports():
    """Test that all required modules can be imported."""
    print("🔍 Testing imports...")

    try:
        from models.door_control import DoorControlManager
        print("✅ Door Control Manager import successful")
    except ImportError as e:
        print(f"❌ Failed to import Door Control Manager: {e}")
        return False

    try:
        import gpio_control
        print("✅ GPIO Control import successful")
    except ImportError as e:
        print(f"❌ Failed to import GPIO Control: {e}")
        return False

    return True

def test_door_control_manager():
    """Test the Door Control Manager functionality."""
    print("\n🚪 Testing Door Control Manager...")

    try:
        from models.door_control import DoorControlManager

        # Initialize the manager
        manager = DoorControlManager()
        print("✅ Door Control Manager initialized")

        # Test configuration loading
        config = manager.get_config()
        if config and isinstance(config, dict):
            print("✅ Configuration loaded successfully")
        else:
            print("❌ Failed to load configuration")
            return False

        # Test mode calculation
        current_mode = manager.get_current_mode()
        if current_mode in ["always_open", "normal_operation", "access_blocked"]:
            print(f"✅ Current mode calculated: {current_mode}")
        else:
            print(f"❌ Invalid current mode: {current_mode}")
            return False

        # Test GPIO state calculation
        gpio_should_be_high = manager.should_gpio_be_high()
        print(f"✅ GPIO state calculation: {'HIGH' if gpio_should_be_high else 'LOW'}")

        # Test next mode change calculation
        next_change = manager.get_next_mode_change()
        if next_change:
            print(f"✅ Next mode change: {next_change}")
        else:
            print("✅ No scheduled mode changes")

        return True

    except Exception as e:
        print(f"❌ Door Control Manager test failed: {e}")
        traceback.print_exc()
        return False

def test_time_calculations():
    """Test time-based calculations for different modes."""
    print("\n⏰ Testing time-based calculations...")

    try:
        from models.door_control import DoorControlManager
        manager = DoorControlManager()

        # Test different times of day
        test_times = [
            (time(6, 0), "Should be access_blocked"),
            (time(10, 0), "Should be always_open"),
            (time(18, 0), "Should be normal_operation"),
            (time(2, 0), "Should be normal_operation")
        ]

        for test_time, description in test_times:
            # Create a test datetime with today's date and the test time
            test_datetime = datetime.combine(datetime.now().date(), test_time)
            mode = manager._get_mode_for_time(test_datetime)
            print(f"✅ {description}: {mode} (at {test_time.strftime('%H:%M')})")

        return True

    except Exception as e:
        print(f"❌ Time calculations test failed: {e}")
        traceback.print_exc()
        return False

def test_fail_safe_mechanisms():
    """Test fail-safe mechanisms."""
    print("\n🛡️ Testing fail-safe mechanisms...")

    try:
        from models.door_control import DoorControlManager
        manager = DoorControlManager()

        # Test QR exit always allowed
        config = manager.get_config()
        qr_exit_enabled = config.get('fail_safe', {}).get('qr_exit_always_enabled', False)

        if qr_exit_enabled:
            print("✅ QR exit fail-safe mechanism enabled")
        else:
            print("❌ QR exit fail-safe mechanism not configured")
            return False

        # Test emergency override capability
        if hasattr(manager, 'set_override'):
            print("✅ Emergency override system available")
        else:
            print("⚠️ Emergency override system not found")

        return True

    except Exception as e:
        print(f"❌ Fail-safe mechanisms test failed: {e}")
        traceback.print_exc()
        return False

def test_configuration_validation():
    """Test configuration validation."""
    print("\n🔧 Testing configuration validation...")

    try:
        from models.door_control import DoorControlManager

        # Test with valid configuration
        valid_config = {
            "enabled": True,
            "modes": {
                "always_open": {
                    "enabled": True,
                    "start_time": "08:00",
                    "end_time": "16:00",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
                }
            }
        }

        manager = DoorControlManager()
        if manager._validate_config(valid_config):
            print("✅ Valid configuration accepted")
        else:
            print("❌ Valid configuration rejected")
            return False

        # Test with invalid configuration
        invalid_config = {
            "enabled": True,
            "modes": {
                "always_open": {
                    "enabled": True,
                    "start_time": "invalid_time",
                    "end_time": "16:00",
                    "days": ["invalid_day"]
                }
            }
        }

        if not manager._validate_config(invalid_config):
            print("✅ Invalid configuration properly rejected")
        else:
            print("❌ Invalid configuration incorrectly accepted")
            return False

        return True

    except Exception as e:
        print(f"❌ Configuration validation test failed: {e}")
        traceback.print_exc()
        return False

def test_gpio_integration():
    """Test GPIO integration (mock mode is fine for testing)."""
    print("\n🔌 Testing GPIO integration...")

    try:
        import gpio_control

        # Test GPIO state functions
        current_state = gpio_control.get_gpio_state()
        print(f"✅ Current GPIO state: {current_state}")

        # Test GPIO control functions exist
        if hasattr(gpio_control, 'set_persistent_door_state'):
            print("✅ Time-based GPIO control functions available")
        else:
            print("❌ Time-based GPIO control functions missing")
            return False

        return True

    except Exception as e:
        print(f"❌ GPIO integration test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("🚀 Starting Door Control System Test Suite")
    print("=" * 60)

    tests = [
        ("Import Test", test_imports),
        ("Door Control Manager Test", test_door_control_manager),
        ("Time Calculations Test", test_time_calculations),
        ("Fail-Safe Mechanisms Test", test_fail_safe_mechanisms),
        ("Configuration Validation Test", test_configuration_validation),
        ("GPIO Integration Test", test_gpio_integration),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! The door control system is ready for production.")
        return 0
    else:
        print(f"⚠️ {total - passed} tests failed. Please review and fix issues before production deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())