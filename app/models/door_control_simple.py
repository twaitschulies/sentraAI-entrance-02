"""
Simplified Door Control Manager to fix deadlock issues.

This is a production-ready, simplified version that avoids the complex
threading and locking issues that were causing worker timeouts.
"""

import json
import os
from datetime import datetime, time
from typing import Dict, Optional
from threading import Thread, Event
import time as time_module

from ..logger import log_system, log_error
from ..config import DATA_DIR

DOOR_CONTROL_FILE = os.path.join(DATA_DIR, "door_control.json")

class SimpleDoorControlManager:
    """Simplified door control manager without complex threading."""

    def __init__(self):
        """Initialize the manager."""
        self.current_mode = "normal_operation"
        self.last_mode_change = datetime.now()
        self._monitoring_thread = None
        self._stop_monitoring = Event()
        self._load_config()
        # Immediately sync GPIO state on initialization
        self.get_current_mode()
        # Start background monitoring
        self._start_monitoring()

    def _load_config(self) -> None:
        """Load door control configuration from file."""
        try:
            if os.path.exists(DOOR_CONTROL_FILE):
                with open(DOOR_CONTROL_FILE, 'r') as f:
                    self.config = json.load(f)

                # CRITICAL FIX: Ensure "mode" field exists, default to "always_normal" if missing
                if "mode" not in self.config:
                    self.config["mode"] = "always_normal"
                    self._save_config()
                    log_system("Door control config missing 'mode' field - set to 'always_normal' (default)")
                else:
                    log_system("Door control configuration loaded successfully")
            else:
                # Create default configuration
                self.config = self._get_default_config()
                self._save_config()
                log_system("Default door control configuration created")
        except Exception as e:
            log_error(f"Error loading door control config: {str(e)}")
            self.config = self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Get default door control configuration."""
        return {
            "enabled": True,
            "mode": "always_normal",  # Options: time_based, always_normal, always_open, always_closed
            "modes": {
                "always_open": {
                    "enabled": False,  # Disabled by default - admin must explicitly enable
                    "start_time": "08:00",
                    "end_time": "16:00",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
                },
                "normal_operation": {
                    "enabled": False,  # Disabled by default when mode is "always_normal"
                    "start_time": "16:00",
                    "end_time": "04:00",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                },
                "access_blocked": {
                    "enabled": False,  # Disabled by default - admin must explicitly enable
                    "start_time": "04:00",
                    "end_time": "08:00",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                }
            },
            "fail_safe": {
                "qr_exit_always_enabled": True
            }
        }

    def _save_config(self) -> bool:
        """Save configuration to file."""
        try:
            os.makedirs(os.path.dirname(DOOR_CONTROL_FILE), exist_ok=True)
            with open(DOOR_CONTROL_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            log_error(f"Error saving door control config: {str(e)}")
            return False

    def _is_time_in_window(self, current_time: time, start_str: str, end_str: str) -> bool:
        """Check if current time is within the specified window."""
        try:
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            # Handle overnight windows (e.g., 22:00 to 06:00)
            if start_time > end_time:
                return current_time >= start_time or current_time <= end_time
            else:
                return start_time <= current_time <= end_time
        except Exception as e:
            log_error(f"Error parsing time window {start_str}-{end_str}: {e}")
            return False

    def get_current_mode(self) -> str:
        """
        Determine current active mode based on time and configuration.

        Returns:
            str: "always_open", "normal_operation", or "access_blocked"
        """
        try:
            if not self.config.get("enabled", False):
                log_system("Door control disabled - defaulting to normal_operation")
                return "normal_operation"

            # Check if we have a manual mode override
            manual_mode = self.config.get("mode", "time_based")
            log_system(f"Door control mode setting: {manual_mode}")

            # Handle manual mode overrides
            if manual_mode == "always_normal":
                self.current_mode = "normal_operation"
                self._sync_gpio_state()
                return "normal_operation"
            elif manual_mode == "always_open":
                self.current_mode = "always_open"
                self._sync_gpio_state()
                return "always_open"
            elif manual_mode == "always_closed":
                self.current_mode = "access_blocked"
                self._sync_gpio_state()
                return "access_blocked"

            # Time-based mode logic
            current_time = datetime.now()
            current_weekday = current_time.strftime("%A").lower()
            log_system(f"Time-based mode check - Current: {current_time.strftime('%H:%M')} on {current_weekday}")

            # Check each mode to see if we're currently in its time window
            modes_config = self.config.get("modes", {})

            for mode_name, mode_config in modes_config.items():
                if not mode_config.get("enabled", False):
                    log_system(f"Mode '{mode_name}' is DISABLED - skipping")
                    continue

                if current_weekday not in mode_config.get("days", []):
                    log_system(f"Mode '{mode_name}' not active on {current_weekday} - skipping")
                    continue

                start_time = mode_config.get("start_time", "00:00")
                end_time = mode_config.get("end_time", "23:59")

                if self._is_time_in_window(current_time.time(), start_time, end_time):
                    log_system(f"✅ Mode '{mode_name}' is ACTIVE ({start_time}-{end_time})")
                    # Always sync GPIO when we determine the mode, even if mode hasn't changed
                    # This ensures GPIO state is correct after service restarts or config changes
                    if mode_name != self.current_mode:
                        self.current_mode = mode_name
                        self.last_mode_change = current_time
                        log_system(f"🔄 Door mode CHANGED to: {mode_name}")
                    self._sync_gpio_state()
                    return mode_name
                else:
                    log_system(f"Mode '{mode_name}' outside time window ({start_time}-{end_time})")

            # Fallback to normal operation if no mode matches
            if self.current_mode != "normal_operation":
                self.current_mode = "normal_operation"
                self.last_mode_change = current_time
                log_system("Door mode defaulted to: normal_operation")
            self._sync_gpio_state()  # Always sync GPIO state

            return "normal_operation"

        except Exception as e:
            log_error(f"Error in get_current_mode: {str(e)}")
            return "normal_operation"

    def should_gpio_be_high(self) -> bool:
        """
        Determine if GPIO should be HIGH based on current mode.

        Returns:
            bool: True if GPIO should be HIGH, False otherwise
        """
        try:
            current_mode = self.get_current_mode()
            return current_mode == "always_open"
        except Exception as e:
            log_error(f"Error determining GPIO state: {str(e)}")
            return False

    def _sync_gpio_state(self) -> None:
        """Synchronize GPIO state with current mode."""
        try:
            from ..gpio_control import set_gpio_state

            if self.current_mode == "always_open":
                success = set_gpio_state(True)  # Set HIGH
                if success:
                    log_system("🟢 GPIO set to HIGH for always_open mode")
                else:
                    log_error("❌ Failed to set GPIO HIGH")
            else:
                success = set_gpio_state(False)  # Set LOW
                if success:
                    log_system("🔴 GPIO set to LOW for normal/blocked mode")
                else:
                    log_error("❌ Failed to set GPIO LOW")

        except Exception as e:
            log_error(f"Error syncing GPIO state: {str(e)}")

    def get_config(self) -> Dict:
        """Get current configuration."""
        return self.config.copy()

    def update_config(self, new_config: Dict) -> bool:
        """Update configuration."""
        try:
            self.config.update(new_config)
            self._save_config()
            log_system("Door control configuration updated")
            # Immediately sync GPIO state after config update
            self.get_current_mode()  # This will trigger _sync_gpio_state
            return True
        except Exception as e:
            log_error(f"Error updating door control config: {str(e)}")
            return False

    def can_access_with_nfc(self) -> bool:
        """Check if NFC access is allowed in current mode."""
        current_mode = self.get_current_mode()
        return current_mode in ["always_open", "normal_operation"]

    def can_access_with_qr(self) -> bool:
        """Check if QR access is allowed (should always be true for fail-safe)."""
        # QR access is ALWAYS allowed for emergency egress (fail-safe)
        # This ensures people can exit even in access_blocked mode
        # The GPIO pulse will still be triggered for QR scans in Mode 3
        return True  # Always return True for fail-safe emergency exit

    def get_status(self) -> Dict:
        """Get comprehensive door control status."""
        current_mode = self.get_current_mode()
        next_change = self.get_next_mode_change()

        try:
            from ..gpio_control import get_gpio_state
            gpio_status = get_gpio_state()
            gpio_state = "HIGH" if gpio_status.get("state") == 1 else "LOW"
        except Exception as e:
            log_error(f"Error getting GPIO state: {str(e)}")
            gpio_state = "UNKNOWN"

        return {
            "enabled": self.config.get("enabled", False),
            "mode": self.config.get("mode", "time_based"),
            "current_mode": current_mode,
            "gpio_state": gpio_state,
            "next_change": next_change,
            "last_mode_change": self.last_mode_change.isoformat() if self.last_mode_change else None,
            "modes_config": self.config.get("modes", {}),
            "timestamp": datetime.now().isoformat()
        }

    def _get_mode_display_name(self, mode_name: str) -> str:
        """Translate internal mode name to German display name."""
        mode_names = {
            'always_open': 'Daueroffen',
            'normal_operation': 'Normalbetrieb',
            'access_blocked': 'Zugang gesperrt'
        }
        return mode_names.get(mode_name, mode_name)

    def get_next_mode_change(self) -> Optional[str]:
        """Get description of next mode change (simplified version)."""
        try:
            current_time = datetime.now()
            current_weekday = current_time.strftime("%A").lower()

            # Find the next time change today
            times = []
            for mode_name, mode_config in self.config.get("modes", {}).items():
                if mode_config.get("enabled", False) and current_weekday in mode_config.get("days", []):
                    start_time = datetime.strptime(mode_config.get("start_time", "00:00"), "%H:%M").time()
                    times.append((start_time, mode_name))

            times.sort()

            for time_obj, mode_name in times:
                if time_obj > current_time.time():
                    mode_display = self._get_mode_display_name(mode_name)
                    return f"{time_obj.strftime('%H:%M')} - {mode_display}"

            # Next change is tomorrow
            if times:
                mode_display = self._get_mode_display_name(times[0][1])
                return f"Morgen {times[0][0].strftime('%H:%M')} - {mode_display}"

            return None

        except Exception as e:
            log_error(f"Error calculating next mode change: {str(e)}")
            return None

    def _start_monitoring(self) -> None:
        """Start background thread for monitoring mode changes and GPIO sync."""
        if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
            self._stop_monitoring.clear()
            self._monitoring_thread = Thread(target=self._monitoring_loop, daemon=True)
            self._monitoring_thread.start()
            log_system("Door control monitoring thread started")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop for automatic mode transitions and GPIO sync."""
        while not self._stop_monitoring.is_set():
            try:
                # Check current mode (this will trigger GPIO sync)
                self.get_current_mode()

                # Sleep for 30 seconds before next check
                self._stop_monitoring.wait(30)

            except Exception as e:
                log_error(f"Error in door control monitoring loop: {str(e)}")
                # Sleep longer on error to prevent spam
                self._stop_monitoring.wait(60)

    def shutdown(self) -> None:
        """Shutdown the door control manager and cleanup resources."""
        try:
            log_system("Shutting down door control manager")
            self._stop_monitoring.set()

            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=5)

            log_system("Door control manager shutdown completed")
        except Exception as e:
            log_error(f"Error during door control manager shutdown: {str(e)}")


# Create singleton instance
simple_door_control_manager = SimpleDoorControlManager()