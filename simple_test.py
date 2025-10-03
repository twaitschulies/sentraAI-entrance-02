#!/usr/bin/env python3
"""
Simple test for door control functionality without background threads.
"""

import sys
import os
import logging

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Minimal logging
logging.basicConfig(level=logging.CRITICAL)  # Only show critical errors

def simple_test():
    """Simple test of door control functionality."""
    print("🔧 Simple Door Control Test")
    print("=" * 30)

    try:
        # Test configuration loading and basic logic only
        from app.models.door_control import DoorControlManager
        from datetime import datetime, time

        # Create instance but avoid starting monitoring
        manager = DoorControlManager()
        manager._stop_monitoring.set()  # Stop monitoring immediately

        # Test basic functionality
        print("✅ Manager created successfully")

        # Test current mode determination (without GPIO sync)
        current_mode = manager.get_current_mode()
        print(f"✅ Current mode: {current_mode}")

        # Test access logic
        nfc_allowed, nfc_reason = manager.should_allow_nfc_access()
        print(f"✅ NFC access: {nfc_allowed} - {nfc_reason}")

        qr_allowed, qr_reason = manager.should_allow_qr_access(is_exit=True)
        print(f"✅ QR exit (fail-safe): {qr_allowed} - {qr_reason}")

        # Test GPIO state logic
        gpio_high = manager.should_gpio_be_high()
        print(f"✅ GPIO should be HIGH: {gpio_high}")

        # Test config access
        config = manager.get_config()
        print(f"✅ Config loaded, enabled: {config.get('enabled', False)}")

        # Shutdown cleanly
        manager.shutdown()
        print("✅ Shutdown completed")

        print("\n🎉 Simple test passed!")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simple_test()
    sys.exit(0 if success else 1)