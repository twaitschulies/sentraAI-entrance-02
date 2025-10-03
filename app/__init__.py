import os
import sys
import traceback
from flask import Flask
from app.routes import bp as routes_bp
from app.unified_logger import unified_logger, log_info, log_warning, log_error, log_system
from app.models.user import user_manager
from app.config import DEFAULT_ADMIN, DATA_DIR

# Absoluter Pfad zum Basisverzeichnis
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Umgebung erkennen - Nur Produktionsmodus
PRODUCTION_MODE = True

# === Sicherstellen, dass benötigte Dateien existieren ===
def ensure_files():
    required_files = ["barcode_database.txt", "permanent_barcodes.txt", "scan_log.txt"]

    # Stelle sicher, dass das Datenverzeichnis existiert
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
            print(f"📁 Datenverzeichnis erstellt: {DATA_DIR}")
        except PermissionError:
            print(f"⚠️ Keine Berechtigung zum Erstellen des Datenverzeichnisses: {DATA_DIR}")
            print(f"Bitte führen Sie aus: sudo mkdir -p {DATA_DIR} && sudo chown -R $USER:$USER {DATA_DIR}")
            # Nicht abbrechen, versuche mit den anderen Dateien fortzufahren
        except Exception as e:
            print(f"⚠️ Fehler beim Erstellen des Datenverzeichnisses: {e}")
            print(traceback.format_exc())

    # Stelle sicher, dass das Logs-Verzeichnis existiert
    logs_dir = os.path.join(BASE_DIR, "logs")
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
            print(f"📁 Logs-Verzeichnis erstellt: {logs_dir}")
        except PermissionError:
            print(f"⚠️ Keine Berechtigung zum Erstellen des Log-Verzeichnisses: {logs_dir}")
            print(f"Bitte führen Sie aus: sudo mkdir -p {logs_dir} && sudo chown -R $USER:$USER {logs_dir}")
        except Exception as e:
            print(f"⚠️ Fehler beim Erstellen des Log-Verzeichnisses: {e}")
            print(traceback.format_exc())

    for filename in required_files:
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            try:
                with open(path, "w") as f:
                    pass  # leere Datei anlegen
                print(f"📄 Datei erstellt: {filename}")
            except PermissionError:
                print(f"⚠️ Keine Berechtigung zum Erstellen der Datei: {path}")
            except Exception as e:
                print(f"⚠️ Fehler beim Erstellen der Datei {filename}: {e}")
                print(traceback.format_exc())

    # Stellen Sie sicher, dass die JSON-Datendateien mit gültigen leeren Strukturen existieren
    scan_data_file = os.path.join(DATA_DIR, "scan_data.json")
    if not os.path.exists(scan_data_file):
        try:
            with open(scan_data_file, "w") as f:
                f.write('{"recent_scans": [], "used_codes": {}}')
            print(f"📄 Leere Scan-Daten-Datei erstellt: {scan_data_file}")
        except PermissionError:
            print(f"⚠️ Keine Berechtigung zum Erstellen der Datei: {scan_data_file}")
        except Exception as e:
            print(f"⚠️ Fehler beim Erstellen der Scan-Daten-Datei: {e}")
            print(traceback.format_exc())
    
    nfc_cards_file = os.path.join(DATA_DIR, "nfc_cards.json")
    if not os.path.exists(nfc_cards_file):
        try:
            with open(nfc_cards_file, "w") as f:
                f.write('{"registered_cards": {}, "recent_card_scans": []}')
            print(f"📄 Leere NFC-Karten-Datei erstellt: {nfc_cards_file}")
        except PermissionError:
            print(f"⚠️ Keine Berechtigung zum Erstellen der Datei: {nfc_cards_file}")
        except Exception as e:
            print(f"⚠️ Fehler beim Erstellen der NFC-Karten-Datei: {e}")
            print(traceback.format_exc())

# Versuche, die Dateien sicherzustellen
try:
    ensure_files()
except Exception as e:
    print(f"⚠️ Fehler beim Erstellen von Dateien: {e}")
    print(traceback.format_exc())

# === Default-Admin erstellen, wenn keine Benutzer existieren ===
def ensure_default_admin():
    try:
        users = user_manager.get_all_users()
        if not users:
            # Erstelle Default-Admin
            user_manager.create_user(
                username=DEFAULT_ADMIN["username"],
                password=DEFAULT_ADMIN["password"],
                role=DEFAULT_ADMIN["role"]
            )
            print(f"👤 Default Admin-Benutzer erstellt: {DEFAULT_ADMIN['username']}")
    except Exception as e:
        print(f"⚠️ Fehler beim Erstellen des Admin-Benutzers: {e}")
        print(traceback.format_exc())

# === Flask-App initialisieren ===
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supergeheimerkey1234567890")  # Umgebungsvariable für Produktion

# === Logging konfigurieren ===
try:
    # Unified logger is already initialized on import
    log_system("SentraAI Entrance System starting up...")
    log_info("Unified logging system initialized successfully")
except Exception as e:
    print(f"⚠️ Fehler beim Einrichten des Loggings: {e}")
    print(traceback.format_exc())

# === Routen registrieren ===
app.register_blueprint(routes_bp)

# === Stelle sicher, dass ein Admin-Benutzer existiert ===
try:
    with app.app_context():
        ensure_default_admin()
except Exception as e:
    print(f"⚠️ Fehler beim Initialisieren des Admin-Benutzers: {e}")
    print(traceback.format_exc())

# Importiere Start-Funktionen für Scanner und NFC-Reader
# Verwende einen sicheren Try-Except-Block, um sicherzustellen, dass die App
# auch dann startet, wenn die Reader nicht initialisiert werden können
scanner_started = False
nfc_reader_started = False

# Produktionsmodus - Nur echte Hardware
print("✅ PRODUKTIONSMODUS AKTIV: Nur echte Hardware-Zugriffe")

try:
    # Importiere Scanner-Modul
    from app.scanner import start_scanner
    # Starte Scanner-Thread
    start_scanner()
    scanner_started = True
    print("✅ QR-Scanner erfolgreich gestartet")
except Exception as e:
    print(f"⚠️ Fehler beim Starten des QR-Scanners: {e}")
    print(traceback.format_exc())

try:
    # Importiere NFC-Reader-Modul
    from app.nfc_reader import start_nfc_reader
    # Starte NFC-Reader-Thread
    start_nfc_reader()
    nfc_reader_started = True
    print("✅ NFC-Kartenleser erfolgreich gestartet")
except Exception as e:
    print(f"⚠️ Fehler beim Starten des NFC-Kartenlesers: {e}")
    print(traceback.format_exc())

print(f"✅ Anwendung initialisiert (Scanner: {scanner_started}, NFC: {nfc_reader_started})")
print("🔧 System bereit - Vereinfachte Version:")
print("   - WebGUI für Admin-Panel")
print("   - NFC-Kartenleser für Zutrittskontrolle")
print("   - QR/Barcode-Scanner für Codes")
print("   - GPIO-Türsteuerung")
