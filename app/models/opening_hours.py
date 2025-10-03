import json
import os
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional, Tuple
from ..config import DATA_DIR
from ..logger import log_system, log_error

OPENING_HOURS_FILE = os.path.join(DATA_DIR, "opening_hours.json")

class OpeningHoursManager:
    """Manages opening hours for the access control system."""

    def __init__(self):
        """Initialize the OpeningHoursManager and load configuration."""
        self.hours = {}
        self._load_hours()

    def _load_hours(self) -> None:
        """Load opening hours from the JSON file."""
        try:
            if os.path.exists(OPENING_HOURS_FILE):
                with open(OPENING_HOURS_FILE, 'r') as f:
                    self.hours = json.load(f)
                log_system("Opening hours configuration loaded successfully")
            else:
                # Default configuration: 24/7 access
                self.hours = {
                    "enabled": False,  # By default, time restrictions are disabled
                    "default_access": True,  # When disabled, allow access
                    "door_state": "normal",  # "always_open", "normal", "always_closed"
                    "weekdays": {
                        "monday": {"enabled": True, "start": "08:00", "end": "18:00"},
                        "tuesday": {"enabled": True, "start": "08:00", "end": "18:00"},
                        "wednesday": {"enabled": True, "start": "08:00", "end": "18:00"},
                        "thursday": {"enabled": True, "start": "08:00", "end": "18:00"},
                        "friday": {"enabled": True, "start": "08:00", "end": "18:00"},
                        "saturday": {"enabled": False, "start": "09:00", "end": "13:00"},
                        "sunday": {"enabled": False, "start": "00:00", "end": "00:00"}
                    },
                    "holidays": [],  # List of dates in ISO format when access is restricted
                    "exceptions": []  # List of dates with special hours
                }
                self._save_hours()
                log_system("Default opening hours configuration created")
        except Exception as e:
            log_error(f"Error loading opening hours: {str(e)}")
            self.hours = {"enabled": False, "default_access": True}

    def _save_hours(self) -> bool:
        """Save opening hours to the JSON file."""
        try:
            os.makedirs(os.path.dirname(OPENING_HOURS_FILE), exist_ok=True)
            with open(OPENING_HOURS_FILE, 'w') as f:
                json.dump(self.hours, f, indent=2)
            log_system("Opening hours configuration saved successfully")
            return True
        except Exception as e:
            log_error(f"Error saving opening hours: {str(e)}")
            return False

    def get_door_state(self) -> str:
        """
        Get the current door state.

        Returns:
            String: "always_open", "normal", or "always_closed"
        """
        return self.hours.get("door_state", "normal")

    def set_door_state(self, state: str) -> bool:
        """
        Set the door state.

        Args:
            state: "always_open", "normal", or "always_closed"

        Returns:
            True if successful, False otherwise
        """
        valid_states = ["always_open", "normal", "always_closed"]
        if state not in valid_states:
            log_error(f"Invalid door state: {state}. Must be one of {valid_states}")
            return False

        try:
            self.hours["door_state"] = state
            self._save_hours()
            log_system(f"Door state updated to: {state}")

            # Synchronize physical GPIO state with configured door state
            self._sync_gpio_state(state)

            return True
        except Exception as e:
            log_error(f"Error setting door state: {str(e)}")
            return False

    def _sync_gpio_state(self, state: str) -> None:
        """
        Synchronize the physical GPIO state with the configured door state.

        Args:
            state: The door state to sync to
        """
        try:
            from ..gpio_control import set_persistent_door_state
            set_persistent_door_state(state)
        except ImportError:
            log_error("GPIO control module not available for state synchronization")
        except Exception as e:
            log_error(f"Error synchronizing GPIO state: {str(e)}")

    def initialize_door_state(self) -> None:
        """
        Initialize the physical door state on system startup.
        Should be called when the system starts to ensure GPIO matches configuration.
        """
        try:
            current_state = self.get_door_state()
            self._sync_gpio_state(current_state)
            log_system(f"Door state initialized to: {current_state}")
        except Exception as e:
            log_error(f"Error initializing door state: {str(e)}")

    def is_access_allowed(self, check_time: Optional[datetime] = None, scan_type: str = "nfc") -> Tuple[bool, str]:
        """
        Check if access is allowed at the given time.

        Args:
            check_time: The time to check (defaults to current time)
            scan_type: Type of scan ("nfc" or "qr") - affects always_closed behavior

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Check door state first
        door_state = self.get_door_state()

        if door_state == "always_open":
            return (True, "Door is set to always open")
        elif door_state == "always_closed":
            if scan_type == "qr":
                # QR/barcode scans are allowed even in always_closed mode (emergency exit)
                return (True, "QR scan allowed in always closed mode (emergency exit)")
            else:
                return (False, "Door is set to always closed")

        # Normal mode - check time restrictions
        if not self.hours.get("enabled", False):
            return (True, "Time restrictions disabled")

        if check_time is None:
            check_time = datetime.now()

        # Check if it's a holiday
        date_str = check_time.date().isoformat()
        if date_str in self.hours.get("holidays", []):
            return (False, "Access denied: Holiday")

        # Check for exceptions (special dates with different hours)
        exceptions = self.hours.get("exceptions", [])
        for exception in exceptions:
            if exception.get("date") == date_str:
                if not exception.get("enabled", False):
                    return (False, f"Access denied: Special closure on {date_str}")

                start_time = datetime.strptime(exception.get("start", "00:00"), "%H:%M").time()
                end_time = datetime.strptime(exception.get("end", "23:59"), "%H:%M").time()
                current_time = check_time.time()

                if start_time <= current_time <= end_time:
                    return (True, f"Access allowed: Special hours on {date_str}")
                else:
                    return (False, f"Outside special hours for {date_str}")

        # Check regular weekday hours
        weekday = check_time.strftime("%A").lower()
        day_config = self.hours.get("weekdays", {}).get(weekday, {})

        if not day_config.get("enabled", False):
            return (False, f"Access denied: Closed on {weekday.capitalize()}")

        start_time = datetime.strptime(day_config.get("start", "00:00"), "%H:%M").time()
        end_time = datetime.strptime(day_config.get("end", "23:59"), "%H:%M").time()
        current_time = check_time.time()

        if start_time <= current_time <= end_time:
            return (True, f"Access allowed: Within {weekday.capitalize()} hours")
        else:
            return (False, f"Outside operating hours for {weekday.capitalize()}")

    def update_hours(self, config: Dict) -> bool:
        """
        Update the opening hours configuration.

        Args:
            config: New configuration dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            self.hours.update(config)
            self._save_hours()
            log_system("Opening hours updated successfully")
            return True
        except Exception as e:
            log_error(f"Error updating opening hours: {str(e)}")
            return False

    def get_hours(self) -> Dict:
        """Get the current opening hours configuration."""
        return self.hours.copy()

    def add_holiday(self, date_str: str) -> bool:
        """
        Add a holiday date.

        Args:
            date_str: Date in ISO format (YYYY-MM-DD)

        Returns:
            True if successful, False otherwise
        """
        try:
            if "holidays" not in self.hours:
                self.hours["holidays"] = []

            if date_str not in self.hours["holidays"]:
                self.hours["holidays"].append(date_str)
                self._save_hours()
                log_system(f"Holiday added: {date_str}")
                return True
            return False
        except Exception as e:
            log_error(f"Error adding holiday: {str(e)}")
            return False

    def remove_holiday(self, date_str: str) -> bool:
        """
        Remove a holiday date.

        Args:
            date_str: Date in ISO format (YYYY-MM-DD)

        Returns:
            True if successful, False otherwise
        """
        try:
            if "holidays" in self.hours and date_str in self.hours["holidays"]:
                self.hours["holidays"].remove(date_str)
                self._save_hours()
                log_system(f"Holiday removed: {date_str}")
                return True
            return False
        except Exception as e:
            log_error(f"Error removing holiday: {str(e)}")
            return False

    def add_exception(self, date_str: str, enabled: bool, start: str, end: str) -> bool:
        """
        Add an exception date with special hours.

        Args:
            date_str: Date in ISO format (YYYY-MM-DD)
            enabled: Whether access is allowed on this date
            start: Start time (HH:MM)
            end: End time (HH:MM)

        Returns:
            True if successful, False otherwise
        """
        try:
            if "exceptions" not in self.hours:
                self.hours["exceptions"] = []

            # Remove existing exception for this date
            self.hours["exceptions"] = [
                e for e in self.hours["exceptions"]
                if e.get("date") != date_str
            ]

            # Add new exception
            self.hours["exceptions"].append({
                "date": date_str,
                "enabled": enabled,
                "start": start,
                "end": end
            })

            self._save_hours()
            log_system(f"Exception added for {date_str}")
            return True
        except Exception as e:
            log_error(f"Error adding exception: {str(e)}")
            return False

    def remove_exception(self, date_str: str) -> bool:
        """
        Remove an exception date.

        Args:
            date_str: Date in ISO format (YYYY-MM-DD)

        Returns:
            True if successful, False otherwise
        """
        try:
            if "exceptions" in self.hours:
                original_length = len(self.hours["exceptions"])
                self.hours["exceptions"] = [
                    e for e in self.hours["exceptions"]
                    if e.get("date") != date_str
                ]

                if len(self.hours["exceptions"]) < original_length:
                    self._save_hours()
                    log_system(f"Exception removed for {date_str}")
                    return True
            return False
        except Exception as e:
            log_error(f"Error removing exception: {str(e)}")
            return False

# Create a singleton instance
opening_hours_manager = OpeningHoursManager()