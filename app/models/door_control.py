"""
Time-based GPIO Door Control System for Raspberry Pi 4b Physical Security
Production-ready door control with three time-based modes and fail-safe behavior.
"""

import json
import os
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Tuple, List
from threading import Thread, Event, Lock
import logging
import traceback
from ..config import DATA_DIR
from ..logger import log_system, log_error

logger = logging.getLogger(__name__)

DOOR_CONTROL_FILE = os.path.join(DATA_DIR, "door_control.json")

class DoorControlManager:
    """
    Comprehensive time-based door control system with three modes:
    1. Always Open - GPIO HIGH (typically 08:00-16:00)
    2. Normal Operation - GPIO LOW with NFC/QR access (typically 16:00-04:00)
    3. Access Blocked - GPIO LOW, NFC blocked, QR exit only (typically 04:00-08:00)
    """

    def __init__(self):
        """Initialize the door control manager with production settings."""
        self.config = {}
        self.current_mode = "normal_operation"
        self.last_mode_change = None
        self.mode_lock = Lock()
        self._monitoring_thread = None
        self._stop_monitoring = Event()
        self._load_config()
        self._start_monitoring()

    def _load_config(self) -> None:
        """Load door control configuration from JSON file."""
        try:
            if os.path.exists(DOOR_CONTROL_FILE):
                with open(DOOR_CONTROL_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                log_system("Door control configuration loaded successfully")
            else:
                # Default configuration - clean slate with no pre-configured times
                # ALL modes disabled by default and no time slots configured
                self.config = {
                    "enabled": True,
                    "modes": {
                        "always_open": {
                            "enabled": False,  # Disabled by default
                            "start_time": "",  # No pre-configured time
                            "end_time": "",    # No pre-configured time
                            "days": []         # No pre-configured days
                        },
                        "normal_operation": {
                            "enabled": True,   # Default to Normal Operation mode
                            "start_time": "00:00",
                            "end_time": "23:59",
                            "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                        },
                        "access_blocked": {
                            "enabled": False,  # Disabled by default
                            "start_time": "",  # No pre-configured time
                            "end_time": "",    # No pre-configured time
                            "days": []         # No pre-configured days
                        }
                    },
                    "override": {
                        "active": False,
                        "mode": None,
                        "expires": None
                    },
                    "fail_safe": {
                        "qr_exit_always_enabled": True,
                        "power_loss_recovery": True,
                        "emergency_override_pin": None
                    }
                }
                self._save_config()
                log_system("Default door control configuration created")
        except Exception as e:
            log_error(f"Error loading door control configuration: {str(e)}")
            self.config = {"enabled": False}

    def _save_config(self) -> bool:
        """Save door control configuration to JSON file."""
        try:
            os.makedirs(os.path.dirname(DOOR_CONTROL_FILE), exist_ok=True)
            with open(DOOR_CONTROL_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            log_system("Door control configuration saved successfully")
            return True
        except Exception as e:
            log_error(f"Error saving door control configuration: {str(e)}")
            return False

    def get_current_mode(self) -> str:
        """
        Determine current active mode based on time and configuration.

        Returns:
            str: "always_open", "normal_operation", or "access_blocked"
        """
        try:
            # Use timeout on lock to avoid deadlocks
            if self.mode_lock.acquire(timeout=5):
                try:
                    if not self.config.get("enabled", False):
                        return "normal_operation"

                    # Check for active override
                    override = self.config.get("override", {})
                    if override.get("active", False):
                        expires = override.get("expires")
                        if expires and datetime.fromisoformat(expires) > datetime.now():
                            mode = override.get("mode", "normal_operation")
                            log_system(f"Using override mode: {mode} (expires: {expires})")
                            return mode
                        else:
                            # Override expired, clear it
                            self.config["override"]["active"] = False
                            self._save_config()

                    current_time = datetime.now()
                    current_weekday = current_time.strftime("%A").lower()

                    # Check each mode to see if we're currently in its time window
                    modes_config = self.config.get("modes", {})

                    for mode_name, mode_config in modes_config.items():
                        if not mode_config.get("enabled", False):
                            continue

                        if current_weekday not in mode_config.get("days", []):
                            continue

                        if self._is_time_in_window(
                            current_time.time(),
                            mode_config.get("start_time", "00:00"),
                            mode_config.get("end_time", "23:59")
                        ):
                            if mode_name != self.current_mode:
                                self.current_mode = mode_name
                                self.last_mode_change = current_time
                                log_system(f"Door mode changed to: {mode_name}")
                                self._sync_gpio_state()
                            return mode_name

                    # Fallback to normal operation if no mode matches
                    if self.current_mode != "normal_operation":
                        self.current_mode = "normal_operation"
                        self.last_mode_change = current_time
                        log_system("Door mode defaulted to: normal_operation")
                        self._sync_gpio_state()

                    return "normal_operation"
                finally:
                    self.mode_lock.release()
            else:
                log_error("Failed to acquire mode lock within timeout")
                return "normal_operation"
        except Exception as e:
            log_error(f"Error determining current mode: {str(e)}")
            return "normal_operation"

    def _is_time_in_window(self, check_time: time, start: str, end: str) -> bool:
        """
        Check if a time falls within a time window, handling overnight periods.

        Args:
            check_time: Time to check
            start: Start time string (HH:MM)
            end: End time string (HH:MM)

        Returns:
            bool: True if time is in window
        """
        try:
            start_time = datetime.strptime(start, "%H:%M").time()
            end_time = datetime.strptime(end, "%H:%M").time()

            if start_time <= end_time:
                # Same day window (e.g., 08:00 - 16:00)
                return start_time <= check_time <= end_time
            else:
                # Overnight window (e.g., 22:00 - 06:00)
                return check_time >= start_time or check_time <= end_time
        except Exception as e:
            log_error(f"Error checking time window: {str(e)}")
            return False

    def should_gpio_be_high(self) -> bool:
        """
        Determine if GPIO should be HIGH based on current mode.

        Returns:
            bool: True if GPIO should be HIGH, False for LOW
        """
        mode = self.get_current_mode()

        if mode == "always_open":
            return True
        elif mode in ["normal_operation", "access_blocked"]:
            return False
        else:
            # Unknown mode, default to safe state (LOW)
            log_error(f"Unknown door mode: {mode}, defaulting to LOW")
            return False

    def should_allow_nfc_access(self) -> Tuple[bool, str]:
        """
        Check if NFC access should be allowed based on current mode.

        Returns:
            Tuple[bool, str]: (allowed, reason)
        """
        mode = self.get_current_mode()

        if mode == "always_open":
            return (True, "Door is in always open mode - NFC access allowed")
        elif mode == "normal_operation":
            return (True, "Normal operation mode - NFC access allowed")
        elif mode == "access_blocked":
            return (False, "Access is blocked - NFC entry denied")
        else:
            return (False, f"Unknown mode: {mode} - NFC access denied")

    def should_allow_qr_access(self, is_exit: bool = True) -> Tuple[bool, str]:
        """
        Check if QR/barcode access should be allowed (fail-safe for exits).

        Args:
            is_exit: Whether this is an exit scan (always allowed for safety)

        Returns:
            Tuple[bool, str]: (allowed, reason)
        """
        # Fail-safe: QR exits are ALWAYS allowed for emergency egress
        if is_exit and self.config.get("fail_safe", {}).get("qr_exit_always_enabled", True):
            return (True, "QR exit always allowed (fail-safe)")

        mode = self.get_current_mode()

        if mode == "always_open":
            return (True, "Door is in always open mode - QR access allowed")
        elif mode == "normal_operation":
            return (True, "Normal operation mode - QR access allowed")
        elif mode == "access_blocked":
            if is_exit:
                return (True, "QR exit allowed even in blocked mode (fail-safe)")
            else:
                return (False, "Access is blocked - QR entry denied")
        else:
            if is_exit:
                return (True, f"Unknown mode: {mode} - QR exit allowed (fail-safe)")
            else:
                return (False, f"Unknown mode: {mode} - QR entry denied")

    def get_next_mode_change(self) -> Optional[Dict]:
        """
        Calculate when the next mode change will occur.

        Returns:
            Optional[Dict]: Next change info or None if no changes
        """
        try:
            if not self.config.get("enabled", False):
                return None

            current_time = datetime.now()
            next_changes = []

            modes_config = self.config.get("modes", {})

            for mode_name, mode_config in modes_config.items():
                if not mode_config.get("enabled", False):
                    continue

                start_time_str = mode_config.get("start_time", "00:00")

                # Calculate next occurrence of this mode's start time
                for day_offset in range(8):  # Check next 7 days
                    check_date = current_time.date() + timedelta(days=day_offset)
                    check_weekday = check_date.strftime("%A").lower()

                    if check_weekday not in mode_config.get("days", []):
                        continue

                    # Create datetime for the mode start time
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                    mode_start_datetime = datetime.combine(check_date, start_time)

                    # Only consider future times
                    if mode_start_datetime > current_time:
                        next_changes.append({
                            "mode": mode_name,
                            "datetime": mode_start_datetime,
                            "time_until": mode_start_datetime - current_time
                        })
                        break

            # Return the earliest next change
            if next_changes:
                next_changes.sort(key=lambda x: x["datetime"])
                next_change = next_changes[0]

                return {
                    "mode": next_change["mode"],
                    "datetime": next_change["datetime"].isoformat(),
                    "time_until_seconds": int(next_change["time_until"].total_seconds()),
                    "time_until_human": self._format_time_until(next_change["time_until"])
                }

            return None

        except Exception as e:
            log_error(f"Error calculating next mode change: {str(e)}")
            return None

    def _format_time_until(self, delta: timedelta) -> str:
        """Format timedelta as human-readable string."""
        try:
            total_seconds = int(delta.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                return f"{hours}h {minutes}m"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        except Exception:
            return "unknown"

    def _sync_gpio_state(self) -> None:
        """Synchronize physical GPIO state with current mode."""
        try:
            from ..gpio_control import sync_gpio_with_time_based_control

            success = sync_gpio_with_time_based_control()
            if success:
                log_system(f"GPIO synchronized successfully for mode: {self.current_mode}")
            else:
                log_error(f"Failed to synchronize GPIO for mode: {self.current_mode}")

        except ImportError:
            log_error("GPIO control module not available for state synchronization")
        except Exception as e:
            log_error(f"Error synchronizing GPIO state: {str(e)}")

    def _start_monitoring(self) -> None:
        """Start background thread for monitoring mode changes."""
        if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
            self._stop_monitoring.clear()
            self._monitoring_thread = Thread(target=self._monitoring_loop, daemon=True)
            self._monitoring_thread.start()
            log_system("Door control monitoring thread started")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop for automatic mode transitions."""
        while not self._stop_monitoring.is_set():
            try:
                # Check current mode (this will trigger mode change if needed)
                self.get_current_mode()

                # Sleep for 30 seconds before next check
                self._stop_monitoring.wait(30)

            except Exception as e:
                log_error(f"Error in door control monitoring loop: {str(e)}")
                log_error(traceback.format_exc())
                # Sleep longer on error to prevent spam
                self._stop_monitoring.wait(60)

    def set_override(self, mode: str, duration_hours: float) -> bool:
        """
        Set a temporary mode override.

        Args:
            mode: Mode to override to ("always_open", "normal_operation", "access_blocked")
            duration_hours: How long the override should last in hours

        Returns:
            bool: True if successful
        """
        valid_modes = ["always_open", "normal_operation", "access_blocked"]
        if mode not in valid_modes:
            log_error(f"Invalid override mode: {mode}")
            return False

        try:
            expires = datetime.now() + timedelta(hours=duration_hours)

            self.config["override"] = {
                "active": True,
                "mode": mode,
                "expires": expires.isoformat()
            }

            if self._save_config():
                log_system(f"Door mode override set: {mode} for {duration_hours} hours")
                # Trigger immediate mode check
                self.get_current_mode()
                return True
            else:
                return False

        except Exception as e:
            log_error(f"Error setting mode override: {str(e)}")
            return False

    def clear_override(self) -> bool:
        """Clear any active mode override."""
        try:
            self.config["override"]["active"] = False
            if self._save_config():
                log_system("Door mode override cleared")
                # Trigger immediate mode check
                self.get_current_mode()
                return True
            else:
                return False
        except Exception as e:
            log_error(f"Error clearing mode override: {str(e)}")
            return False

    def get_status(self) -> Dict:
        """
        Get comprehensive door control status.

        Returns:
            Dict: Complete status information
        """
        current_mode = self.get_current_mode()
        gpio_should_be_high = self.should_gpio_be_high()
        nfc_allowed, nfc_reason = self.should_allow_nfc_access()
        qr_allowed, qr_reason = self.should_allow_qr_access()
        next_change = self.get_next_mode_change()

        # Get actual GPIO state
        gpio_status = {"state": "unknown", "success": False}
        try:
            from ..gpio_control import get_gpio_state
            gpio_status = get_gpio_state()
        except Exception as e:
            log_error(f"Error getting GPIO state: {str(e)}")

        return {
            "enabled": self.config.get("enabled", False),
            "current_mode": current_mode,
            "last_mode_change": self.last_mode_change.isoformat() if self.last_mode_change else None,
            "gpio": {
                "should_be_high": gpio_should_be_high,
                "actual_state": gpio_status.get("state", "unknown"),
                "hardware_available": gpio_status.get("success", False)
            },
            "access": {
                "nfc_allowed": nfc_allowed,
                "nfc_reason": nfc_reason,
                "qr_allowed": qr_allowed,
                "qr_reason": qr_reason
            },
            "next_change": next_change,
            "override": self.config.get("override", {}),
            "fail_safe": self.config.get("fail_safe", {}),
            "timestamp": datetime.now().isoformat()
        }

    def update_config(self, new_config: Dict) -> bool:
        """
        Update door control configuration.

        Args:
            new_config: New configuration dictionary

        Returns:
            bool: True if successful
        """
        try:
            # Validate configuration structure
            if not self._validate_config(new_config):
                return False

            self.config.update(new_config)
            if self._save_config():
                log_system("Door control configuration updated successfully")
                # Trigger immediate mode check with new config
                self.get_current_mode()
                return True
            else:
                return False

        except Exception as e:
            log_error(f"Error updating door control configuration: {str(e)}")
            return False

    def _validate_config(self, config: Dict) -> bool:
        """Validate configuration structure and values."""
        try:
            # Basic structure validation
            if "modes" in config:
                for mode_name, mode_config in config["modes"].items():
                    if mode_name not in ["always_open", "normal_operation", "access_blocked"]:
                        log_error(f"Invalid mode name: {mode_name}")
                        return False

                    if "start_time" in mode_config or "end_time" in mode_config:
                        # Validate time format
                        for time_field in ["start_time", "end_time"]:
                            if time_field in mode_config:
                                try:
                                    datetime.strptime(mode_config[time_field], "%H:%M")
                                except ValueError:
                                    log_error(f"Invalid time format in {mode_name}.{time_field}: {mode_config[time_field]}")
                                    return False

            return True

        except Exception as e:
            log_error(f"Error validating configuration: {str(e)}")
            return False

    def get_config(self) -> Dict:
        """Get current door control configuration."""
        return self.config.copy()

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
door_control_manager = DoorControlManager()

# Initialize door state on system startup
def initialize_door_control():
    """Initialize door control system on startup."""
    try:
        # Just load config, don't sync GPIO to avoid lock contention at startup
        door_control_manager._load_config()
        log_system("Door control system initialized successfully")
    except Exception as e:
        log_error(f"Error initializing door control system: {str(e)}")

# Call initialization when module is imported
initialize_door_control()