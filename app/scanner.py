# Safe import for evdev - nicht verfügbar auf allen Systemen
try:
    from evdev import InputDevice, list_devices, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    # Mock-Definitionen für Tests
    InputDevice = None
    list_devices = lambda: []
    categorize = lambda x: None
    ecodes = type('ecodes', (), {'EV_KEY': 1, 'KEY_ENTER': 28})()
from datetime import datetime, timedelta
from threading import Thread, Lock
from app.gpio_control import pulse, pulse_with_door_state_check
from app.models.opening_hours import opening_hours_manager
import logging
import os
import json
import requests
import time
import traceback
from requests.auth import HTTPDigestAuth

logger = logging.getLogger(__name__)

# Import des Webhook-Managers für Barcode-Events
try:
    from .webhook_manager import trigger_barcode_webhook
    WEBHOOK_AVAILABLE = True
    logger.info("✅ Webhook-Manager für Barcodes geladen")
except ImportError as e:
    WEBHOOK_AVAILABLE = False
    logger.warning(f"Webhook-Manager nicht verfügbar: {e}")
    def trigger_barcode_webhook(*args, **kwargs):
        return False

# Load app settings to check for allow_all_barcodes setting
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def load_scanner_settings():
    """Load scanner settings from config.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                settings = json.load(f)
                return settings.get('allow_all_barcodes', False)
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Scanner-Konfiguration: {e}")
    return False

recent_scans = []
MAX_SCANS = 100
ENABLE_AUDIO_TRIGGER = os.getenv("ENABLE_AUDIO_TRIGGER", "false").lower() == "true"
# Pfad zur Scan-Daten-Datei
SCAN_DATA_FILE = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data", "scan_data.json")
# Verzeichnis für Scan-Daten-Datei erstellen, falls es nicht existiert
os.makedirs(os.path.dirname(SCAN_DATA_FILE), exist_ok=True)
# Intervall für die Gerätewiederverbindung in Sekunden
RECONNECT_INTERVAL = 5

# Health Check und Monitoring für Scanner
scanner_consecutive_failures = 0
MAX_SCANNER_FAILURES = 5
last_device_count = 0

# Thread-Sicherheit
scan_data_lock = Lock()

def scanner_health_check():
    """Health Check für Scanner-Geräte."""
    global scanner_consecutive_failures, last_device_count
    
    try:
        if not EVDEV_AVAILABLE:
            return
        current_devices = list_devices()
        device_count = len(current_devices)
        
        if device_count > 0:
            scanner_consecutive_failures = 0
            if device_count != last_device_count:
                logger.info(f"🔋 Scanner Health Check: {device_count} Geräte erkannt")
                last_device_count = device_count
            return True
        else:
            scanner_consecutive_failures += 1
            if scanner_consecutive_failures >= MAX_SCANNER_FAILURES:
                logger.warning("⚠️ Keine Scanner-Geräte gefunden - prüfe USB-Verbindungen")
                # Selbstheilung: udev neu laden
                try:
                    import subprocess
                    subprocess.run(['sudo', 'udevadm', 'control', '--reload-rules'], 
                                 check=False, timeout=5)
                    scanner_consecutive_failures = 0
                    logger.info("🔄 udev-Regeln neu geladen")
                except Exception as e:
                    logger.error(f"Fehler beim Neuladen der udev-Regeln: {e}")
            return False
    except Exception as e:
        scanner_consecutive_failures += 1
        logger.error(f"Scanner Health Check Fehler: {e}")
        return False

def enhanced_scanner_reconnect():
    """Erweiterte Wiederverbindungslogik für Scanner."""
    base_interval = RECONNECT_INTERVAL
    max_interval = 30  # Maximal 30 Sekunden für Scanner
    
    interval = min(base_interval * (2 ** min(scanner_consecutive_failures, 3)), max_interval)
    
    if scanner_consecutive_failures > 0:
        logger.info(f"🔄 Scanner Reconnect: Warte {interval}s (Fehler: {scanner_consecutive_failures})")
    
    return interval

def load_codes():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path = os.path.join(base_dir, "barcode_database.txt")
    perm_path = os.path.join(base_dir, "permanent_barcodes.txt")

    db_codes = set()
    perm_codes = set()

    try:
        if os.path.exists(db_path):
            with open(db_path, "r") as f:
                for line in f:
                    code = line.strip()
                    if code:
                        db_codes.add(code)
    except Exception as e:
        logger.error(f"Fehler beim Laden der temporären Codes: {e}")
        logger.error(traceback.format_exc())

    try:
        if os.path.exists(perm_path):
            with open(perm_path, "r") as f:
                for line in f:
                    code = line.strip()
                    if code:
                        perm_codes.add(code)
    except Exception as e:
        logger.error(f"Fehler beim Laden der permanenten Codes: {e}")
        logger.error(traceback.format_exc())

    return db_codes, perm_codes

# Funktion, um sicherzustellen, dass wir immer die aktuellsten Daten haben
def get_current_scans():
    global recent_scans
    
    # Lade Daten aus der Datei, wenn vorhanden
    if os.path.exists(SCAN_DATA_FILE):
        try:
            with open(SCAN_DATA_FILE, 'r') as f:
                data = json.load(f)
                loaded_scans = data.get('recent_scans', [])
                # Aktualisiere die globale Variable
                recent_scans = loaded_scans
        except json.JSONDecodeError as e:
            logger.error(f"Fehler beim Decodieren der JSON-Datei in get_current_scans: {e}")
            # Versuche, die Datei zu reparieren, indem wir eine neue leere Struktur schreiben
            try:
                with open(SCAN_DATA_FILE, 'w') as f:
                    json.dump({"recent_scans": [], "used_codes": {}}, f)
                logger.info("Scan-Daten-Datei wurde repariert")
            except Exception as write_error:
                logger.error(f"Konnte Scan-Daten-Datei nicht reparieren: {write_error}")
        except Exception as e:
            logger.error(f"Fehler beim Laden der Scan-Daten in get_current_scans: {e}")
            logger.error(traceback.format_exc())
    
    return recent_scans

# Funktion zum Laden der gespeicherten Scan-Daten
def load_scan_data():
    global recent_scans, used_codes
    
    logger.info(f"Versuche Scan-Daten zu laden aus: {SCAN_DATA_FILE}")
    
    if os.path.exists(SCAN_DATA_FILE):
        try:
            with open(SCAN_DATA_FILE, 'r') as f:
                data = json.load(f)
                
                # Lade die Scan-Daten
                loaded_scans = data.get('recent_scans', [])
                logger.info(f"Geladene Scan-Daten: {len(loaded_scans)} Scans")
                if loaded_scans:
                    logger.info(f"Neuester geladener Scan: {loaded_scans[-1]}")
                
                # Aktualisiere die globale Variable
                recent_scans = loaded_scans
                
                # Konvertiere die Zeitstempel in den used_codes zurück zu datetime
                temp_used_codes = data.get('used_codes', {})
                for code, timestamps in temp_used_codes.items():
                    used_codes[code] = [datetime.fromisoformat(ts) for ts in timestamps]
                
                logger.info(f"Scan-Daten erfolgreich geladen: {len(recent_scans)} Scans")
                
        except json.JSONDecodeError as e:
            logger.error(f"Fehler beim Decodieren der JSON-Datei: {e}")
            # Versuche, die Datei zu reparieren
            try:
                with open(SCAN_DATA_FILE, 'w') as f:
                    json.dump({"recent_scans": [], "used_codes": {}}, f)
                logger.info("Scan-Daten-Datei wurde repariert")
                recent_scans = []
                used_codes = {}
            except Exception as write_error:
                logger.error(f"Konnte Scan-Daten-Datei nicht reparieren: {write_error}")
                logger.error(traceback.format_exc())
                recent_scans = []
                used_codes = {}
        except Exception as e:
            logger.error(f"Fehler beim Laden der Scan-Daten: {e}")
            # Traceback für bessere Fehleranalyse
            logger.error(traceback.format_exc())
            # Setze auf leere Listen/Dicts bei Fehler
            recent_scans = []
            used_codes = {}
    else:
        logger.info(f"Keine gespeicherten Scan-Daten gefunden unter {SCAN_DATA_FILE}, starte mit leeren Daten")
        # Stelle sicher, dass die Datei mit einer gültigen leeren Struktur existiert
        try:
            with open(SCAN_DATA_FILE, 'w') as f:
                json.dump({"recent_scans": [], "used_codes": {}}, f)
            logger.info("Leere Scan-Daten-Datei erstellt")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der leeren Scan-Daten-Datei: {e}")
            logger.error(traceback.format_exc())
        
        recent_scans = []
        used_codes = {}

# Funktion zum Speichern der Scan-Daten
def save_scan_data():
    """Speichert Scan-Daten thread-sicher in der JSON-Datei."""
    with scan_data_lock:
        try:
            # Vorbereiten der Daten zum Speichern
            # Konvertiere datetime-Objekte zu Strings für JSON
            serializable_used_codes = {}
            for code, timestamps in used_codes.items():
                serializable_used_codes[code] = [ts.isoformat() for ts in timestamps]
            
            data = {
                'recent_scans': recent_scans.copy(),  # Thread-sicheres Kopieren
                'used_codes': serializable_used_codes
            }
            
            # Temporäre Datei verwenden, um Datenverlust zu vermeiden
            temp_file = SCAN_DATA_FILE + '.tmp'
            with open(temp_file, 'w', buffering=8192) as f:  # Optimierte Puffergröße
                json.dump(data, f, separators=(',', ':'))  # Kompakte JSON
            
            # Atomare Umbenennung für sicheres Speichern
            os.replace(temp_file, SCAN_DATA_FILE)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Scan-Daten: {e}")
            logger.error(traceback.format_exc())

barcode_db, permanent_codes = load_codes()
used_codes = {}
# Lade bestehende Scan-Daten beim Start
load_scan_data()

def trigger_audio_clip():
    url = "http://172.16.1.130/axis-cgi/playclip.cgi"
    params = {
        "location": "Ansage.mp3",
        "repeat": "0",
        "volume": "50",
        "audiodeviceid": "0",
        "audiooutputid": "0"
    }
    auth = HTTPDigestAuth("root", "EBXv22xQ5psObPb2qO")

    try:
        response = requests.get(url, params=params, auth=auth, timeout=5)
        if response.status_code == 200:
            logger.info("🔊 Audio-Clip erfolgreich gestartet")
        else:
            logger.warning(f"⚠️ Audio-Clip konnte nicht gestartet werden: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Triggern des Audio-Clips: {e}")

def handle_scan(code):
    # Lade die Codes neu bei jedem Scan
    global barcode_db, permanent_codes, recent_scans
    barcode_db, permanent_codes = load_codes()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    
    # Prüfe ob "Alle Barcodes erlauben" Modus aktiviert ist
    allow_all_barcodes = load_scanner_settings()
    
    # Bestimme den Status des Scans
    scan_status = "Ungültig"
    if allow_all_barcodes:
        # Wenn "Alle Barcodes erlauben" aktiviert ist, erlaube alle Codes
        scan_status = "Alle erlaubt"
    elif code in permanent_codes:
        scan_status = "Permanent"
    elif code in barcode_db:
        uses = used_codes.get(code, [])
        uses = [u for u in uses if now - u < timedelta(hours=24)]
        if len(uses) >= 2 and (uses[1] - uses[0] <= timedelta(minutes=5)):
            scan_status = "Gesperrt"
        else:
            scan_status = "Temporär"
    
    # Füge den Scan mit Status zur Liste hinzu
    scan_data = {
        "timestamp": timestamp,
        "code": code,
        "status": scan_status
    }
    recent_scans.append(scan_data)
    # Detailliertes Logging nur bei wichtigen Ereignissen
    if scan_status in ["Permanent", "Temporär", "Alle erlaubt"]:
        logger.info(f"✅ Gültiger Scan: {code} ({scan_status})")
    elif scan_status == "Gesperrt":
        logger.warning(f"⛔️ Gesperrter Scan: {code}")
    
    # Stelle sicher, dass die Liste nicht zu groß wird
    if len(recent_scans) > MAX_SCANS:
        removed = recent_scans.pop(0)
    
    # Speichere die Scan-Daten nach jeder Änderung
    save_scan_data()

    # Verarbeite den Scan
    scan_successful = False
    scan_status = 'unknown'
    
    if allow_all_barcodes:
        logger.info(f"✅ Code erlaubt (Alle Barcodes Modus): {code}")
        scan_successful = True
        scan_status = 'allowed_all'
    elif code in permanent_codes:
        logger.info(f"✅ Permanenter Code erkannt: {code}")
        scan_successful = True
        scan_status = 'permanent'
    elif code in barcode_db:
        uses = used_codes.get(code, [])
        uses = [u for u in uses if now - u < timedelta(hours=24)]
        used_codes[code] = uses

        if len(uses) >= 2 and (uses[1] - uses[0] <= timedelta(minutes=5)):
            logger.warning(f"⛔️ Code {code} wurde bereits 2× in 5 Minuten genutzt. Gesperrt für 24 Stunden.")
            scan_status = 'blocked'
            save_scan_data()  # Speichere Änderungen an used_codes
            return

        if not uses:
            logger.info(f"✅ Erster Scan: {code}")
            used_codes[code].append(now)
            scan_successful = True
            scan_status = 'first_use'
        elif len(uses) == 1 and now - uses[0] <= timedelta(minutes=5):
            logger.info(f"✅ Zweiter Versuch innerhalb 5 Minuten: {code}")
            used_codes[code].append(now)
            scan_successful = True
            scan_status = 'second_use'
        elif len(uses) == 1:
            logger.warning(f"⛔️ Zweiter Versuch zu spät (>5 Min): {code}")
            scan_status = 'too_late'
        else:
            logger.warning(f"⛔️ Code {code} ist nach 2 Versuchen gesperrt für 24h")
            scan_status = 'exhausted'
    else:
        logger.warning(f"⛔️ Ungültiger Scan abgewiesen: {code}")
        scan_status = 'invalid'
    
    # Webhook SOFORT triggern bei erfolgreichem Scan (OPTIMIERT für schnelle Ansage)
    # IMPORTANT: Webhook is triggered INDEPENDENTLY of "Allow All Barcodes" setting
    # Both features must work simultaneously without conflict
    if scan_successful and WEBHOOK_AVAILABLE:
        try:
            webhook_data = {
                'code': code,
                'status': scan_status,
                'scan_type': 'barcode'
            }
            # Webhook in separatem Thread für maximale Geschwindigkeit
            import threading
            webhook_thread = threading.Thread(target=trigger_barcode_webhook, args=(webhook_data, False))
            webhook_thread.daemon = True
            webhook_thread.start()
            logger.debug("🚀 Barcode-Webhook in separatem Thread gestartet")
        except Exception as webhook_err:
            logger.debug(f"Barcode-Webhook Fehler: {webhook_err}")
    
    # GPIO-Puls und Audio NACH Webhook für optimales Timing
    if scan_successful:
        # Check time-based door control before opening door (QR scan type with fail-safe)
        try:
            from app.models.door_control_simple import simple_door_control_manager as door_control_manager

            # FAIL-SAFE: QR scans are ALWAYS allowed for emergency egress
            # This is a critical safety feature - even in Mode 3 (access_blocked)
            # QR/barcode scans must trigger GPIO HIGH for people to exit!
            is_exit = True  # QR scans are treated as exits for fail-safe behavior
            current_mode = door_control_manager.get_current_mode()

            logger.info(f"🔓 QR-Scan wird verarbeitet im Modus: {current_mode} (Fail-Safe aktiv)")

            # Use time-based door control for GPIO pulse with QR fail-safe
            try:
                from app.gpio_control import pulse_with_qr_time_check
                success = pulse_with_qr_time_check()
                if success:
                    logger.info(f"🔓 GPIO-Puls erfolgreich ausgelöst für QR-Code (Mode: {current_mode}, Exit: {is_exit})")
                    if ENABLE_AUDIO_TRIGGER:
                        trigger_audio_clip()
                else:
                    logger.warning(f"⚠️ GPIO-Puls fehlgeschlagen für QR-Code (Mode: {current_mode})")
            except Exception as gpio_err:
                logger.error(f"Fehler beim Auslösen des GPIO-Pulses: {gpio_err}")
                logger.error(traceback.format_exc())
                # Fallback to legacy pulse method for fail-safe operation
                try:
                    pulse_with_door_state_check()
                    logger.debug("🔓 Fallback GPIO-Puls ausgelöst (fail-safe)")
                    if ENABLE_AUDIO_TRIGGER:
                        trigger_audio_clip()
                except Exception as fallback_err:
                    logger.error(f"Auch Fallback GPIO-Puls fehlgeschlagen: {fallback_err}")

        except ImportError as import_err:
            logger.warning(f"Door control manager nicht verfügbar, verwende legacy opening hours mit fail-safe: {import_err}")
            # Fallback to legacy opening hours system with fail-safe behavior
            access_allowed, reason = opening_hours_manager.is_access_allowed(scan_type="qr")

            # FAIL-SAFE: If opening hours system fails or denies access, still allow QR exit
            if not access_allowed:
                logger.warning(f"🚫 Zugang regulär verweigert für Barcode '{code}': {reason}")
                logger.info(f"🚨 Aber QR-Exit wird für fail-safe Verhalten trotzdem gewährt")
                # Log the access with fail-safe notation
                recent_scans.append({
                    "timestamp": datetime.now().isoformat(),
                    "code": code,
                    "status": f"Fail-Safe Zugang (regulär verweigert: {reason})"
                })
                # Still allow the pulse for emergency egress

            try:
                pulse_with_door_state_check()
                logger.debug("🔓 Legacy GPIO-Puls ausgelöst (mit fail-safe)")
                if ENABLE_AUDIO_TRIGGER:
                    trigger_audio_clip()
            except Exception as gpio_err:
                logger.error(f"Fehler beim Auslösen des GPIO-Pulses: {gpio_err}")

        except Exception as door_control_err:
            logger.error(f"Unerwarteter Fehler in door control system: {door_control_err}")
            logger.error(traceback.format_exc())
            # EMERGENCY FAIL-SAFE - always allow QR access in case of system failure
            logger.warning("🚨 Notfall-Fail-Safe: QR-Zugang wird trotz System-Fehler gewährt")
            try:
                pulse_with_door_state_check()
                logger.warning("🚨 Notfall-QR-Zugang gewährt trotz door control Fehler")
                if ENABLE_AUDIO_TRIGGER:
                    trigger_audio_clip()
            except Exception as emergency_err:
                logger.error(f"Auch Notfall-GPIO-Puls fehlgeschlagen: {emergency_err}")
                # At this point, the physical security system is compromised
                logger.critical("🔥 KRITISCH: Kompletter GPIO-Ausfall - Physische Sicherheit beeinträchtigt!")
    
    # Speichere die Scan-Daten nur bei Änderungen an used_codes
    # Nicht erneut speichern, wurde bereits oben gemacht

def barcode_scanner_listener():
    logger.info("🔍 Scanner-Listener gestartet – warte auf eingehendes Signal...")

    keycode_to_char = {
        "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4",
        "KEY_5": "5", "KEY_6": "6", "KEY_7": "7", "KEY_8": "8",
        "KEY_9": "9", "KEY_0": "0", "KEY_A": "A", "KEY_B": "B",
        "KEY_C": "C", "KEY_D": "D", "KEY_E": "E", "KEY_F": "F",
        "KEY_G": "G", "KEY_H": "H", "KEY_I": "I", "KEY_J": "J",
        "KEY_K": "K", "KEY_L": "L", "KEY_M": "M", "KEY_N": "N",
        "KEY_O": "O", "KEY_P": "P", "KEY_Q": "Q", "KEY_R": "R",
        "KEY_S": "S", "KEY_T": "T", "KEY_U": "U", "KEY_V": "V",
        "KEY_W": "W", "KEY_X": "X", "KEY_Y": "Y", "KEY_Z": "Z",
        "KEY_MINUS": "-", "KEY_EQUAL": "=", "KEY_SLASH": "/",
        "KEY_ENTER": "\n"
    }

    # Halte Informationen über alle bekannten Geräte
    device_paths = set()
    threads = []
    running = True

    def scan_for_devices():
        nonlocal device_paths, threads
        
        while running:
            try:
                if not EVDEV_AVAILABLE:
                    time.sleep(1)
                    continue
                current_devices = set(list_devices())
                
                # Prüfe auf neue Geräte
                new_devices = current_devices - device_paths
                for device_path in new_devices:
                    try:
                        if not EVDEV_AVAILABLE:
                            continue
                        device = InputDevice(device_path)
                        logger.info(f"Neues Gerät erkannt: {device.name} ({device_path})")
                        device_paths.add(device_path)
                        t = Thread(target=listen_on_device, args=(device,), daemon=True)
                        t.start()
                        threads.append(t)
                    except Exception as e:
                        logger.error(f"Fehler beim Verbinden mit Gerät {device_path}: {e}")
                
                # Health Check durchführen und erweiterte Reconnect-Logik verwenden
                scanner_health_check()
                wait_time = enhanced_scanner_reconnect() if scanner_consecutive_failures > 0 else RECONNECT_INTERVAL
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Fehler beim Scannen nach Geräten: {e}")
                wait_time = enhanced_scanner_reconnect()
                time.sleep(wait_time)

    def listen_on_device(device):
        logger.info(f"🎧 Lausche auf: {device.name} ({device.path})")
        barcode = ""
        try:
            for event in device.read_loop():
                if EVDEV_AVAILABLE and event.type == ecodes.EV_KEY:
                    key_event = categorize(event)
                    if key_event.keystate == key_event.key_down:
                        keycode = key_event.keycode
                        if keycode in keycode_to_char:
                            char = keycode_to_char[keycode]
                            if char == "\n":
                                handle_scan(barcode)
                                barcode = ""
                            else:
                                barcode += char
        except Exception as e:
            logger.warning(f"⚠️ Gerät {device.path} getrennt oder Fehler: {e}")
            # Entferne den Gerätepfad aus dem Set der bekannten Geräte
            if device.path in device_paths:
                device_paths.remove(device.path)

    # Starte den Thread zum kontinuierlichen Geräte-Scanning
    scanner_thread = Thread(target=scan_for_devices, daemon=True)
    scanner_thread.start()

def start_scanner():
    global barcode_db, permanent_codes
    barcode_db, permanent_codes = load_codes()
    # Lade gespeicherte Scan-Daten beim Start
    load_scan_data()
    t = Thread(target=barcode_scanner_listener, daemon=True)
    t.start()
