# Guard NFC QR v2

Ein robustes QR-Code und NFC-Kartenlesegerät-System für Raspberry Pi mit automatischer Türsteuerung und Benutzerprotokollierung.

## 🚀 Features

- **QR-Code Scanner**: Automatisches Scannen von QR-Codes über USB/HID-Eingabegeräte
- **NFC-Kartenleser**: Unterstützung für EMV-kompatible Smartcards und MIFARE-Karten
- **🆕 Allow All Barcodes**: Neuer Modus zum Umgehen aller Sicherheitskontrollen - alle Barcodes werden akzeptiert
- **Automatische Türsteuerung**: GPIO-basierte Relais-Steuerung für Türöffner
- **Smart Code Validation**: 24-Stunden Reset für temporäre Codes, 5-Minuten-Fenster für zweite Nutzung
- **Web-Interface**: Benutzerfreundliche Weboberfläche zur Verwaltung und Überwachung
- **Benutzerprotokollierung**: Umfassende Logs aller Scan-Aktivitäten
- **Automatische Admin-Wiederherstellung**: admin/admin Login wird bei jedem Start sichergestellt
- **Systemmonitoring**: Überwachung von Hardware und Service-Status

## 🛠️ Installation

### Automatische Installation auf Raspberry Pi

```bash
# Repository klonen
git clone https://github.com/twaitschulies/guard-prod-entrance-exit-v2.git
cd guard-prod-entrance-exit-v2

# Installation starten (als Root)
sudo ./install.sh
```

Das Installationsskript:
- Installiert alle erforderlichen Abhängigkeiten
- Konfiguriert systemd-Services
- Richtet nginx als Reverse-Proxy ein
- Konfiguriert udev-Regeln für Hardware-Zugriff
- Startet alle Services automatisch

### Manuelle Installation

```bash
# System-Pakete installieren
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-dev python3-rpi.gpio \
                        nginx git libevdev-dev libudev-dev python3-libevdev evtest \
                        pcscd libpcsclite-dev swig

# Python-Umgebung erstellen
python3 -m venv venv
source venv/bin/activate

# Python-Abhängigkeiten installieren
pip install -r requirements.txt

# Systemd-Service konfigurieren (siehe install.sh für Details)
```

## 🔧 Konfiguration

### Standard-Anmeldedaten

- **Benutzername**: `admin`
- **Passwort**: `admin`

⚠️ **Wichtig**: Die admin/admin Anmeldedaten werden automatisch bei jedem Neustart wiederhergestellt, um sicherzustellen, dass Sie immer Zugriff haben.

### GPIO-Konfiguration

Standardmäßig ist GPIO-Pin 17 für die Türsteuerung konfiguriert. Dies kann in `app/config.py` angepasst werden:

```python
CONTACT_PIN = 17  # GPIO-Pin für den Türöffner
```

### Ports und Services

- **Web-Interface**: Port 80 (http://raspberry-pi-ip/)
- **Anwendung**: Port 8000 (intern)
- **Service-Name**: `qrverification.service`

## 🆕 Allow All Barcodes Feature

### Überblick

Die neue "Allow All Barcodes" Funktion ermöglicht es, **alle** gescannten Barcodes zu akzeptieren und die Tür zu öffnen, unabhängig von der konfigurierten Barcode-Datenbank.

### ⚠️ Sicherheitswarnung

Diese Funktion **umgeht alle Sicherheitskontrollen** und sollte nur in kontrollierten Umgebungen oder zu Testzwecken verwendet werden.

### Aktivierung

1. **Als Benutzer anmelden** (beliebiger Login)
2. **Zu Einstellungen navigieren**
3. **"Alle Barcodes erlauben" aktivieren**
4. **Einstellungen speichern**

### Verhalten

- **Aktiviert**: Jeder gescannte Barcode/QR-Code öffnet die Tür
- **Status**: Alle Scans werden als "Alle erlaubt" protokolliert
- **Deaktiviert**: Normale Validierungsregeln gelten

### Code-Gültigkeitsregeln (Normal-Modus)

| Code-Typ | Gültigkeit | Beschreibung |
|----------|------------|--------------|
| **Permanent** | ♾️ Unbegrenzt | Aus `permanent_barcodes.txt` |
| **Temporär** | 🔄 2× alle 24h | Aus `barcode_database.txt` |
| **Temporär** | ⏱️ 5-Min-Fenster | Zweite Nutzung nur innerhalb 5 Minuten |
| **Gesperrt** | ⛔ 24 Stunden | Nach 2 Nutzungen in <5 Min |

## 🔍 Überwachung und Wartung

### Service-Status prüfen

```bash
sudo systemctl status qrverification
```

### Logs anzeigen

```bash
# Live-Logs verfolgen
sudo journalctl -u qrverification -f

# Letzte 50 Zeilen
sudo journalctl -u qrverification -n 50
```

### Service-Kontrolle

```bash
# Service neustarten
sudo systemctl restart qrverification

# Service stoppen
sudo systemctl stop qrverification

# Service starten
sudo systemctl start qrverification
```

### Debug-Modus aktivieren

```bash
# NFC-Debug-Modus aktivieren
sudo systemctl edit qrverification
```

Fügen Sie hinzu:
```ini
[Service]
Environment=NFC_DEBUG=true
```

## 📱 Web-Interface

Das Web-Interface bietet folgende Funktionen:

- **Dashboard**: Übersicht über System-Status und aktuelle Aktivitäten
- **QR-Codes**: Verwaltung von temporären und permanenten QR-Codes
- **NFC-Karten**: Übersicht über gescannte NFC-Karten
- **Benutzer**: Benutzerverwaltung (nur für Admins)
- **Logs**: Anzeige der System- und Scan-Logs
- **Einstellungen**: Konfiguration der Hardware-Parameter

## 🔌 Hardware-Kompatibilität

### Unterstützte QR-Scanner
- USB-HID-Barcode-Scanner
- Kamera-basierte Scanner (über USB)

### Unterstützte NFC-Reader
- PC/SC-kompatible Smartcard-Reader
- ACR122U und ähnliche
- Alle pyscard-kompatiblen Geräte

### GPIO-Anforderungen
- Raspberry Pi GPIO-Zugriff für Relais-Steuerung
- Standard-Pin: GPIO 17 (anpassbar)

## 🧪 Troubleshooting

### Service startet nicht

```bash
# Detaillierte Logs anzeigen
sudo journalctl -u qrverification --no-pager -l

# Python-Umgebung prüfen
source venv/bin/activate
python3 -c "import flask, evdev, pyscard; print('Alle Module verfügbar')"
```

### NFC-Reader wird nicht erkannt

```bash
# PC/SC-Service prüfen
sudo systemctl status pcscd

# NFC-Reader auflisten
pcsc_scan
```

### GPIO-Fehler

```bash
# GPIO-Berechtigungen prüfen
ls -la /dev/gpiomem

# GPIO-Test
python3 -c "
from app.gpio_control import get_gpio_state, pulse
print('GPIO-Status:', get_gpio_state())
pulse()
"
```

### Admin-Login funktioniert nicht

Das System stellt automatisch sicher, dass admin/admin funktioniert. Falls dennoch Probleme auftreten:

```bash
# Service neustarten (erstellt automatisch funktionierenden Admin)
sudo systemctl restart qrverification

# Manuelle Benutzer-Reparatur
sudo rm -f data/users.json
sudo systemctl restart qrverification
```

## 📊 Architektur

```
├── app/
│   ├── __init__.py          # Flask-App Initialisierung
│   ├── auth.py              # Authentifizierung (veraltet)
│   ├── config.py            # Konfiguration
│   ├── gpio_control.py      # GPIO/Relais-Steuerung
│   ├── logger.py            # Logging-System
│   ├── nfc_reader.py        # NFC-Kartenleser
│   ├── routes.py            # Web-Routen
│   ├── scanner.py           # QR-Code-Scanner
│   ├── system_monitor.py    # Hardware-Monitoring
│   ├── models/
│   │   └── user.py          # Benutzerverwaltung
│   ├── static/              # CSS/JS-Dateien
│   └── templates/           # HTML-Templates
├── data/                    # Benutzer- und Scan-Daten
├── logs/                    # Log-Dateien
├── venv/                    # Python-Umgebung
├── install.sh               # Installations-Skript
├── requirements.txt         # Python-Abhängigkeiten
└── wsgi.py                  # WSGI-Entry-Point
```

## 🤝 Entwicklung

### Lokale Entwicklung

```bash
# Repository klonen
git clone https://github.com/twaitschulies/guard-nfc-qrv2.git
cd guard-nfc-qrv2

# Entwicklungsumgebung einrichten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Entwicklungsserver starten
python3 wsgi.py
```

### Code-Struktur

- **Modular**: Separate Module für Scanner, NFC, GPIO
- **Thread-sicher**: Parallele Verarbeitung von Hardware-Events
- **Fehlerbehandlung**: Robuste Error-Recovery-Mechanismen
- **Logging**: Umfassende Protokollierung aller Aktivitäten

## 📄 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Details finden Sie in der LICENSE-Datei.

## 🆘 Support

Bei Problemen oder Fragen:

1. Prüfen Sie die [Troubleshooting](#-troubleshooting)-Sektion
2. Schauen Sie in die System-Logs: `sudo journalctl -u qrverification -f`
3. Erstellen Sie ein Issue auf GitHub mit detaillierten Informationen über Ihr System und den Fehler

## 🔄 Updates

Um das System zu aktualisieren:

```bash
cd /pfad/zum/projekt
git pull origin main
sudo systemctl restart qrverification
```

## ⚡ Performance-Optimierung

- **Single Worker**: Optimiert für Raspberry Pi Hardware
- **Thread Pool**: Parallele Verarbeitung von Scanner-Events
- **Memory Management**: Automatische Bereinigung von Scan-Logs
- **Health Checks**: Automatische Wiederverbindung bei Hardware-Fehlern 