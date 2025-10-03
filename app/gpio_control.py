import time
import logging
from app.config import CONTACT_PIN
import os
import json
import threading
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

# === Raspberry Pi 5 GPIO-Konfiguration ===
# Forciere lgpio als bevorzugte Pin Factory für Pi 5
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
os.environ['GPIOZERO_PIN_FACTORY_FALLBACK'] = 'lgpio,pigpio,native,mock'

# Thread-Lock für thread-sicheren Zugriff auf GPIO
gpio_lock = threading.Lock()

# GPIO-Status
gpio_hardware_available = False
door_relay = None
gpio_mode = "unknown"

def init_gpio_hardware():
    """Initialisiert die GPIO-Hardware mit verschiedenen Methoden"""
    global door_relay, gpio_hardware_available, gpio_mode
    
    try:
        # Methode 1: gpiozero mit lgpio (Pi 5 optimiert)
        try:
            from gpiozero import Device, LED
            try:
                from gpiozero.pins.lgpio import LgpioFactory
                # Setze lgpio als Pin Factory
                Device.pin_factory = LgpioFactory()
            except (ImportError, AttributeError) as e:
                logger.warning(f"LgpioFactory nicht verfügbar: {e}")
                # Verwende Standard Pin Factory
            
            door_relay = LED(CONTACT_PIN)
            door_relay.off()  # Initialize to LOW state
            gpio_hardware_available = True
            gpio_mode = "gpiozero-lgpio"
            logger.info(f"✅ GPIO-Pin {CONTACT_PIN} erfolgreich konfiguriert (gpiozero + lgpio - Pi 5)")
            return True
            
        except Exception as e:
            logger.warning(f"gpiozero+lgpio fehlgeschlagen: {e}")
        
        # Methode 2: gpiozero Standard (automatische Pin Factory)
        try:
            from gpiozero import LED
            
            door_relay = LED(CONTACT_PIN)
            door_relay.off()
            gpio_hardware_available = True
            gpio_mode = "gpiozero-auto"
            logger.info(f"✅ GPIO-Pin {CONTACT_PIN} konfiguriert (gpiozero automatisch)")
            return True
            
        except Exception as e:
            logger.warning(f"gpiozero automatisch fehlgeschlagen: {e}")
        
        # Methode 3: Direkter lgpio-Zugriff
        try:
            import lgpio
            global lgpio_handle
            
            lgpio_handle = lgpio.gpiochip_open(0)  # Chip 0 für die meisten Pi-Modelle
            lgpio.gpio_claim_output(lgpio_handle, CONTACT_PIN)
            lgpio.gpio_write(lgpio_handle, CONTACT_PIN, 0)  # LOW
            
            gpio_hardware_available = True
            gpio_mode = "lgpio-direct"
            logger.info(f"✅ GPIO-Pin {CONTACT_PIN} konfiguriert (direkter lgpio-Zugriff)")
            return True
            
        except Exception as e:
            logger.warning(f"Direkter lgpio-Zugriff fehlgeschlagen: {e}")
        
        # Methode 4: Mock-Modus mit Warnung
        gpio_hardware_available = False
        gpio_mode = "mock"
        logger.warning("⚠️ GPIO-Hardware nicht verfügbar - verwende MOCK MODE")
        logger.warning("   Für echte GPIO-Kontrolle installieren Sie: sudo pip install lgpio")
        return False
        
    except Exception as e:
        logger.error(f"Kritischer Fehler bei GPIO-Initialisierung: {e}")
        gpio_hardware_available = False
        gpio_mode = "error"
        return False

# Sichere GPIO-Initialisierung nur wenn nicht im Import-Kontext
lgpio_handle = None
try:
    init_gpio_hardware()
except Exception as e:
    logger.error(f"GPIO-Initialisierung fehlgeschlagen: {e}")
    gpio_mode = "error"
    gpio_hardware_available = False

def open_door():
    """Öffnet die Tür, indem der Kontakt aktiviert wird."""
    try:
        settings = load_settings()
        door_open_time = float(settings.get('door_open_time', 1.5))
        
        with gpio_lock:
            success = _set_gpio_high()
            if success:
                time.sleep(door_open_time)
                _set_gpio_low()
                logger.info(f"🟢 Tür geöffnet (GPIO {door_open_time} Sekunden HIGH) - {gpio_mode}")
                return True
            else:
                logger.error("❌ Tür öffnen fehlgeschlagen - GPIO nicht verfügbar")
                return False
                
    except Exception as e:
        logger.error(f"Fehler beim Öffnen der Tür: {e}")
        logger.error(traceback.format_exc())
        return False

def close_door():
    """Schließt die Tür, indem der Kontakt deaktiviert wird."""
    try:
        with gpio_lock:
            success = _set_gpio_low()
            if success:
                logger.info(f"🔴 Tür geschlossen (GPIO LOW) - {gpio_mode}")
                return True
            else:
                logger.error("❌ Tür schließen fehlgeschlagen - GPIO nicht verfügbar")
                return False
                
    except Exception as e:
        logger.error(f"Fehler beim Schließen der Tür: {e}")
        logger.error(traceback.format_exc())
        return False

def _set_gpio_high():
    """Setzt GPIO-Pin auf HIGH - mehrere Methoden"""
    global door_relay, lgpio_handle
    
    if gpio_mode == "gpiozero-lgpio" or gpio_mode == "gpiozero-auto":
        try:
            if door_relay:
                door_relay.on()
                return True
        except Exception as e:
            logger.error(f"gpiozero HIGH fehlgeschlagen: {e}")
    
    elif gpio_mode == "lgpio-direct":
        try:
            if lgpio_handle is not None:
                import lgpio
                lgpio.gpio_write(lgpio_handle, CONTACT_PIN, 1)
                return True
        except Exception as e:
            logger.error(f"lgpio direct HIGH fehlgeschlagen: {e}")
    
    elif gpio_mode == "mock":
        logger.info(f"MockLED pin {CONTACT_PIN}: ON")
        return True
    
    return False

def _set_gpio_low():
    """Setzt GPIO-Pin auf LOW - mehrere Methoden"""
    global door_relay, lgpio_handle
    
    if gpio_mode == "gpiozero-lgpio" or gpio_mode == "gpiozero-auto":
        try:
            if door_relay:
                door_relay.off()
                return True
        except Exception as e:
            logger.error(f"gpiozero LOW fehlgeschlagen: {e}")
    
    elif gpio_mode == "lgpio-direct":
        try:
            if lgpio_handle is not None:
                import lgpio
                lgpio.gpio_write(lgpio_handle, CONTACT_PIN, 0)
                return True
        except Exception as e:
            logger.error(f"lgpio direct LOW fehlgeschlagen: {e}")
    
    elif gpio_mode == "mock":
        logger.info(f"MockLED pin {CONTACT_PIN}: OFF")
        return True
    
    return False

def pulse(duration=2):
    """Sendet einen Puls an den Türöffner."""
    try:
        open_door()
        time.sleep(duration)
        close_door()
        logger.info(f"🟢 Türöffnungspuls für {duration} Sekunden gesendet - {gpio_mode}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Puls-Senden: {e}")
        logger.error(traceback.format_exc())
        
        # Versuche GPIO zurückzusetzen
        try:
            _set_gpio_low()
        except:
            pass
        
        return False

def get_gpio_state():
    """Gibt den aktuellen GPIO-Zustand zurück."""
    try:
        state = False
        
        if gpio_mode == "gpiozero-lgpio" or gpio_mode == "gpiozero-auto":
            if door_relay:
                state = door_relay.is_lit
        elif gpio_mode == "lgpio-direct":
            if lgpio_handle is not None:
                import lgpio
                state = lgpio.gpio_read(lgpio_handle, CONTACT_PIN) == 1
        elif gpio_mode == "mock":
            state = False  # Mock ist immer LOW
        
        return {
            "success": True,
            "pin": CONTACT_PIN,
            "state": 1 if state else 0,
            "mode": gpio_mode,
            "hardware_available": gpio_hardware_available,
            "library": "multi-method",
            "compatible": "Raspberry Pi 5"
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des GPIO-Zustands: {e}")
        return {
            "success": False,
            "error": str(e),
            "mode": gpio_mode,
            "hardware_available": gpio_hardware_available
        }

def cleanup():
    """Bereinigt die GPIO-Ressourcen."""
    global door_relay, lgpio_handle
    
    try:
        if gpio_mode == "gpiozero-lgpio" or gpio_mode == "gpiozero-auto":
            if door_relay:
                door_relay.close()
        elif gpio_mode == "lgpio-direct":
            if lgpio_handle is not None:
                import lgpio
                lgpio.gpiochip_close(lgpio_handle)
                
        logger.info(f"GPIO-Ressourcen bereinigt ({gpio_mode})")
    except Exception as e:
        logger.error(f"Fehler beim Bereinigen der GPIO-Ressourcen: {e}")

# Konfigurationsdatei für Einstellungen - KORRIGIERT: Verwende config.json aus dem Stammverzeichnis
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def load_settings():
    """Lädt Einstellungen aus der Konfigurationsdatei"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Konfiguration: {e}")
    
    return {
        'audio_url': 'http://localhost:8000/audio',
        'volume': 50,
        'username': 'admin',
        'password': 'admin',
        'door_open_time': 1.5
    }

# Legacy-Funktionen für Rückwärtskompatibilität
def open_door_legacy():
    """Legacy function - opens door for 5 seconds."""
    try:
        with gpio_lock:
            success = _set_gpio_high()
            if success:
                time.sleep(5)
                _set_gpio_low()
                logger.info(f"🟢 Tür geöffnet (GPIO 5 Sekunden HIGH) - Legacy Mode ({gpio_mode})")
                return True
            return False
    except Exception as e:
        logger.error(f"Fehler beim Legacy-Türöffnen: {e}")
        return False

# Diagnose-Funktion
def diagnose_gpio():
    """Führt eine GPIO-Diagnose durch"""
    print("🔍 GPIO-Diagnose:")
    print(f"   Modus: {gpio_mode}")
    print(f"   Hardware verfügbar: {gpio_hardware_available}")
    print(f"   Pin: {CONTACT_PIN}")
    
    if gpio_hardware_available:
        print("✅ GPIO-Hardware funktioniert")
    else:
        print("❌ GPIO-Hardware nicht verfügbar")
        print("   Lösung: sudo pip install lgpio")

logger.info(f"GPIO-Modul initialisiert: {gpio_mode} (Hardware: {gpio_hardware_available})")

# Time-based door control state management
time_based_door_state = {"mode": "normal_operation", "gpio_high": False, "last_sync": None}

def set_time_based_door_state(mode: str) -> bool:
    """
    Sets the time-based door state and synchronizes GPIO.

    Args:
        mode: "always_open", "normal_operation", or "access_blocked"

    Returns:
        True if successful, False otherwise
    """
    global time_based_door_state

    try:
        if mode == "always_open":
            # Set GPIO permanently HIGH
            with gpio_lock:
                success = _set_gpio_high()
                if success:
                    time_based_door_state = {
                        "mode": "always_open",
                        "gpio_high": True,
                        "last_sync": datetime.now().isoformat()
                    }
                    logger.info("🟢 Door set to ALWAYS OPEN mode - GPIO permanently HIGH")
                    return True
                else:
                    logger.error("❌ Failed to set door to always open - GPIO not available")
                    return False

        elif mode in ["normal_operation", "access_blocked"]:
            # Set GPIO to LOW for these modes
            with gpio_lock:
                success = _set_gpio_low()
                if success:
                    time_based_door_state = {
                        "mode": mode,
                        "gpio_high": False,
                        "last_sync": datetime.now().isoformat()
                    }
                    logger.info(f"🔴 Door set to {mode.upper()} mode - GPIO LOW")
                    return True
                else:
                    logger.error(f"❌ Failed to set door to {mode} - GPIO not available")
                    return False
        else:
            logger.error(f"❌ Invalid door mode: {mode}")
            return False

    except Exception as e:
        logger.error(f"Error setting time-based door state: {e}")
        logger.error(traceback.format_exc())
        return False

def get_time_based_door_state() -> dict:
    """
    Returns the current time-based door state.

    Returns:
        Dictionary with mode, gpio_high, and last_sync information
    """
    return time_based_door_state.copy()

def pulse_with_time_based_check(duration=2) -> bool:
    """
    Sends a pulse based on current time-based door mode.

    Args:
        duration: Pulse duration in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        from .models.door_control_simple import simple_door_control_manager

        # Check if NFC access should be allowed based on current mode
        nfc_allowed = simple_door_control_manager.can_access_with_nfc()

        if not nfc_allowed:
            logger.info("🚫 NFC access denied in current mode")
            return False

        current_mode = simple_door_control_manager.get_current_mode()

        # If door is in always_open mode, no need to pulse (it's already HIGH)
        if current_mode == "always_open":
            logger.info("🟢 Door is in ALWAYS OPEN mode - no pulse needed (already HIGH)")
            return True

        # Normal pulse operation for other modes
        success = pulse(duration)
        if success:
            logger.info(f"🟢 Door pulse sent successfully in {current_mode} mode")
        else:
            logger.error(f"❌ Door pulse failed in {current_mode} mode")

        return success

    except Exception as e:
        logger.error(f"Error in pulse_with_time_based_check: {e}")
        return False

def pulse_with_qr_time_check(duration=2) -> bool:
    """
    Sends a pulse for QR/barcode scans with fail-safe for emergency exit.

    IMPORTANT: QR/barcode scans MUST work in Mode 3 (access_blocked) for emergency egress!
    This is a critical safety feature - people must be able to exit even when access is blocked.

    Args:
        duration: Pulse duration in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        from .models.door_control_simple import simple_door_control_manager

        # QR access is ALWAYS allowed for emergency exit (fail-safe)
        # Even in Mode 3 (access_blocked), QR exits must work!
        qr_allowed = simple_door_control_manager.can_access_with_qr()

        if not qr_allowed:
            # This should never happen with proper fail-safe, but log it
            logger.error("⚠️ CRITICAL: QR access denied - this violates fail-safe!")
            # Still allow the pulse for emergency exit
            logger.warning("🚨 Overriding denial for emergency exit fail-safe")

        current_mode = simple_door_control_manager.get_current_mode()

        # If door is in always_open mode, no need to pulse (it's already HIGH)
        if current_mode == "always_open":
            logger.info("🟢 Door is in ALWAYS OPEN mode - no pulse needed (already HIGH)")
            return True

        # Always pulse for QR/barcode (including Mode 3 for emergency exit)
        success = pulse(duration)
        if success:
            logger.info(f"🟢 QR/Barcode pulse sent successfully in {current_mode} mode (fail-safe enabled)")
        else:
            logger.error(f"❌ QR/Barcode pulse failed in {current_mode} mode")

        return success

    except Exception as e:
        logger.error(f"Error in pulse_with_qr_time_check: {e}")
        # In case of error, still try to pulse for safety
        try:
            return pulse(duration)
        except:
            return False

def sync_gpio_with_time_based_control() -> bool:
    """
    Synchronizes GPIO state with current time-based door control mode.
    Called by the door control manager to ensure GPIO matches expected state.

    Returns:
        True if successful, False otherwise
    """
    try:
        from .models.door_control_simple import simple_door_control_manager

        current_mode = simple_door_control_manager.get_current_mode()
        should_be_high = simple_door_control_manager.should_gpio_be_high()

        with gpio_lock:
            if should_be_high:
                success = _set_gpio_high()
                logger.info(f"🟢 GPIO synchronized to HIGH for {current_mode} mode")
            else:
                success = _set_gpio_low()
                logger.info(f"🔴 GPIO synchronized to LOW for {current_mode} mode")

            if success:
                time_based_door_state.update({
                    "mode": current_mode,
                    "gpio_high": should_be_high,
                    "last_sync": datetime.now().isoformat()
                })

            return success

    except Exception as e:
        logger.error(f"Error synchronizing GPIO with time-based control: {e}")
        return False

# Legacy persistent door state management (kept for backward compatibility)
persistent_door_state = {"active": False, "mode": "normal"}

def set_persistent_door_state(state: str) -> bool:
    """
    Legacy function for setting persistent door state.
    Maintained for backward compatibility.

    Args:
        state: "always_open", "normal", or "always_closed"

    Returns:
        True if successful, False otherwise
    """
    global persistent_door_state

    try:
        if state == "always_open":
            # Set GPIO permanently HIGH
            with gpio_lock:
                success = _set_gpio_high()
                if success:
                    persistent_door_state = {"active": True, "mode": "always_open"}
                    logger.info("🟢 Door set to ALWAYS OPEN - GPIO permanently HIGH (legacy)")
                    return True
                else:
                    logger.error("❌ Failed to set door to always open - GPIO not available")
                    return False

        elif state == "normal" or state == "always_closed":
            # Reset GPIO to LOW and disable persistent mode
            with gpio_lock:
                success = _set_gpio_low()
                if success:
                    persistent_door_state = {"active": False, "mode": state}
                    logger.info(f"🔴 Door set to {state.upper()} - GPIO normal operation (legacy)")
                    return True
                else:
                    logger.error(f"❌ Failed to set door to {state} - GPIO not available")
                    return False
        else:
            logger.error(f"❌ Invalid door state: {state}")
            return False

    except Exception as e:
        logger.error(f"Error setting persistent door state: {e}")
        logger.error(traceback.format_exc())
        return False

def get_persistent_door_state() -> dict:
    """
    Returns the current persistent door state.

    Returns:
        Dictionary with 'active' and 'mode' keys
    """
    return persistent_door_state.copy()

def pulse_with_door_state_check(duration=2) -> bool:
    """
    Legacy function - sends a pulse only if not in always_open mode.

    Args:
        duration: Pulse duration in seconds

    Returns:
        True if successful or if in always_open mode, False otherwise
    """
    try:
        # If door is set to always open, no need to pulse
        if persistent_door_state.get("mode") == "always_open":
            logger.info("🟢 Door is in ALWAYS OPEN mode - no pulse needed (legacy)")
            return True

        # Normal pulse operation for other modes
        return pulse(duration)

    except Exception as e:
        logger.error(f"Error in pulse_with_door_state_check: {e}")
        return False

def set_gpio_state(high: bool) -> bool:
    """
    Set GPIO pin to HIGH or LOW state.

    Args:
        high: True for HIGH, False for LOW

    Returns:
        True if successful, False otherwise
    """
    try:
        if high:
            return _set_gpio_high()
        else:
            return _set_gpio_low()
    except Exception as e:
        logger.error(f"Error setting GPIO state to {'HIGH' if high else 'LOW'}: {e}")
        return False
