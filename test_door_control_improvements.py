#!/usr/bin/env python3
"""
Test script for door control improvements
Tests that Mode 1 (Always Open) activates GPIO HIGH immediately without NFC scan
"""

import sys
import time
import json
from datetime import datetime

# Add the app directory to path
sys.path.insert(0, '/Users/t.waitschulies/Downloads/guard-test-ee-v3-develop')

from app.models.door_control_simple import simple_door_control_manager
from app.gpio_control import get_gpio_state, set_gpio_state

def test_gpio_immediate_activation():
    """Test that GPIO switches immediately when mode changes"""
    print("=" * 60)
    print("DOOR CONTROL IMPROVEMENTS TEST")
    print("=" * 60)

    # Get initial state
    print("\n1. Checking initial state...")
    initial_mode = simple_door_control_manager.get_current_mode()
    initial_gpio = get_gpio_state()
    print(f"   Initial mode: {initial_mode}")
    print(f"   Initial GPIO state: {initial_gpio.get('state', 'unknown')}")

    # Test updating configuration to always_open mode
    print("\n2. Setting time-based control to Always Open mode...")
    test_config = {
        "enabled": True,
        "modes": {
            "always_open": {
                "enabled": True,
                "start_time": "00:00",
                "end_time": "23:59",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            },
            "normal_operation": {
                "enabled": False,
                "start_time": "16:00",
                "end_time": "04:00",
                "days": []
            },
            "access_blocked": {
                "enabled": False,
                "start_time": "04:00",
                "end_time": "08:00",
                "days": []
            }
        }
    }

    success = simple_door_control_manager.update_config(test_config)
    print(f"   Configuration updated: {success}")

    # Wait a moment for GPIO sync
    time.sleep(1)

    # Check if GPIO went HIGH immediately (without NFC scan)
    print("\n3. Verifying GPIO state after mode change...")
    new_mode = simple_door_control_manager.get_current_mode()
    new_gpio = get_gpio_state()
    print(f"   Current mode: {new_mode}")
    print(f"   GPIO state: {new_gpio.get('state', 'unknown')}")

    if new_mode == "always_open" and new_gpio.get('state') == 1:
        print("   ✅ SUCCESS: GPIO went HIGH immediately in Always Open mode!")
    else:
        print("   ❌ FAILURE: GPIO did not go HIGH as expected")

    # Test switching back to normal mode
    print("\n4. Testing switch to Normal Operation mode...")
    test_config["modes"]["always_open"]["enabled"] = False
    test_config["modes"]["normal_operation"]["enabled"] = True
    test_config["modes"]["normal_operation"]["days"] = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    success = simple_door_control_manager.update_config(test_config)
    print(f"   Configuration updated: {success}")

    # Wait a moment for GPIO sync
    time.sleep(1)

    # Check GPIO state
    normal_mode = simple_door_control_manager.get_current_mode()
    normal_gpio = get_gpio_state()
    print(f"   Current mode: {normal_mode}")
    print(f"   GPIO state: {normal_gpio.get('state', 'unknown')}")

    if normal_mode == "normal_operation" and normal_gpio.get('state') == 0:
        print("   ✅ SUCCESS: GPIO went LOW in Normal Operation mode!")
    else:
        print("   ❌ FAILURE: GPIO did not go LOW as expected")

    # Test monitoring thread
    print("\n5. Testing background monitoring...")
    print("   Waiting 5 seconds to ensure monitoring thread is syncing GPIO...")
    time.sleep(5)

    monitored_gpio = get_gpio_state()
    print(f"   GPIO state after monitoring: {monitored_gpio.get('state', 'unknown')}")
    print(f"   Hardware available: {monitored_gpio.get('hardware_available', False)}")
    print(f"   GPIO mode: {monitored_gpio.get('mode', 'unknown')}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    # Summary
    print("\nSUMMARY:")
    print("- Mode 1 (Always Open) should activate GPIO HIGH immediately: ", end="")
    print("✅ PASSED" if new_mode == "always_open" and new_gpio.get('state') == 1 else "❌ FAILED")
    print("- Normal Operation mode should set GPIO LOW: ", end="")
    print("✅ PASSED" if normal_mode == "normal_operation" and normal_gpio.get('state') == 0 else "❌ FAILED")
    print("- Background monitoring keeps GPIO in sync: ", end="")
    print("✅ ACTIVE" if monitored_gpio.get('hardware_available', False) else "⚠️  NO HARDWARE")

if __name__ == "__main__":
    try:
        test_gpio_immediate_activation()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()