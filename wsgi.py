#!/usr/bin/env python3
import os
import sys
import traceback

# Absoluter Pfad zum Basisverzeichnis
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Verzeichnisse für Daten und Logs sicherstellen mit absoluten Pfaden
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

# Fehlerbehandlung verbessern
try:
    from app import app
except Exception as e:
    error_log_path = os.path.join(BASE_DIR, "logs", "startup_error.log")
    try:
        with open(error_log_path, "a") as f:
            f.write("----- STARTUP ERROR " + os.path.dirname(os.path.abspath(__file__)) + " -----\n")
            f.write(f"Exception: {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("----- END ERROR -----\n")
    except PermissionError:
        # Fallback für den Fall, dass keine Schreibrechte vorliegen
        print(f"ACHTUNG: Keine Schreibrechte für {error_log_path}")
        print(f"Bitte Berechtigungen prüfen mit: sudo chown -R BENUTZER:GRUPPE {BASE_DIR}/logs")
        print(f"Oder ausführen mit: sudo systemctl restart qrverification.service")
    except Exception as log_error:
        print(f"Fehler beim Schreiben des Logs: {log_error}")
    
    # Ausgabe in die Konsole für sofortige Diagnose
    print(f"KRITISCHER FEHLER: {str(e)}")
    print(traceback.format_exc())
    sys.exit(1)

# Nur starten wenn als Hauptmodul aufgerufen
if __name__ == "__main__":
    port = 5001  # Changed from 5000 to avoid AirPlay conflict on macOS
    print(f"\n🚀 Starting server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
