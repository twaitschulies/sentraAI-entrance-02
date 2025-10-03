import os
import json
import secrets
from pathlib import Path

# Anwendungspfade
APP_ROOT = Path(__file__).parent.parent.absolute()
DATA_DIR = os.path.join(APP_ROOT, 'data')
LOGS_DIR = os.path.join(APP_ROOT, 'logs')
LOG_DIR = LOGS_DIR  # Alias for logging_setup.py
LOG_FILE = os.path.join(LOG_DIR, 'app.log')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SCANDATA_FILE = os.path.join(DATA_DIR, 'scan_data.json')

# Erstelle Verzeichnisse falls sie nicht existieren
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# === Raspberry Pi 5 GPIO Konfiguration ===
# Forciere lgpio als bevorzugte Pin Factory für Pi 5
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
# Fallback-Reihenfolge für Pin Factories
os.environ['GPIOZERO_PIN_FACTORY_FALLBACK'] = 'lgpio,pigpio,native'
# Debugging aktivieren (optional)
# os.environ['GPIOZERO_DEBUG'] = '1'

# GPIO-Konfiguration
CONTACT_PIN = 17  # GPIO-Pin für den Türöffner

# Session-Konfiguration
SESSION_TIMEOUT = 60 * 60  # 1 Stunde in Sekunden
SESSION_KEY = 'aiqr_session'
SESSION_COOKIE_SECURE = True  # Nur über HTTPS (in Produktion)
SESSION_COOKIE_HTTPONLY = True  # Verhindert XSS
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF-Schutz

# Sicherheits-Konfiguration
PASSWORD_MIN_LENGTH = 8
# FIXED Salt für konsistente Passwort-Hashes über Installationen hinweg
# Wichtig: Dies stellt sicher, dass admin/admin immer funktioniert
PASSWORD_SALT = os.getenv('AIQR_PASSWORD_SALT') or 'aiqr_guard_v3_2025_fixed_salt_do_not_change'

# Rate Limiting
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW = 900  # 15 Minuten in Sekunden
LOCKOUT_DURATION = 1800     # 30 Minuten in Sekunden

# Benutzer-Konfiguration
DEFAULT_ADMIN = {
    "username": "admin",
    "password": "admin",  # In Produktion sollte dies geändert werden
    "role": "admin",
    "created_at": None  # Wird bei der Erstellung aktualisiert
}

# Log-Konfiguration
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
MAX_LOG_ENTRIES = 1000

# QR-Code-Konfiguration
QR_ERROR_CORRECTION = 'M'  # L, M, Q, H (von niedrig zu hoch)
QR_BOX_SIZE = 10
QR_BORDER = 4

# Anwendungskonfiguration
APP_NAME = "AIQR System"
APP_VERSION = "1.0.0"

# Lade benutzerdefinierte Konfiguration wenn vorhanden
CONFIG_FILE = os.path.join(APP_ROOT, 'config.json')

def load_config():
    """Lädt benutzerdefinierte Konfiguration aus config.json wenn vorhanden"""
    global SESSION_TIMEOUT, CONTACT_PIN, PASSWORD_MIN_LENGTH, LOG_LEVEL
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            # Überschreibe Standard-Werte mit benutzerdefinierten Werten
            SESSION_TIMEOUT = config.get('session_timeout', SESSION_TIMEOUT)
            CONTACT_PIN = config.get('contact_pin', CONTACT_PIN)
            PASSWORD_MIN_LENGTH = config.get('password_min_length', PASSWORD_MIN_LENGTH)
            LOG_LEVEL = config.get('log_level', LOG_LEVEL)
            
        except Exception as e:
            # Fehler beim Laden der Konfiguration ignorieren und Standard-Werte verwenden
            pass

# Versuche, benutzerdefinierte Konfiguration zu laden
load_config()

# Exportiere alle Konfigurationsvariablen
__all__ = [var for var in dir() if not var.startswith('__') and var.isupper()]
