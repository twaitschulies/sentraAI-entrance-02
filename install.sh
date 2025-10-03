#!/bin/bash

# Farbdefinitionen für die Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Progress-Counter
TOTAL_STEPS=17
CURRENT_STEP=0

# Funktion für Progress-Anzeige
show_progress() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    local percentage=$((CURRENT_STEP * 100 / TOTAL_STEPS))
    local bar_length=50
    local filled_length=$((percentage * bar_length / 100))
    
    printf "\r${CYAN}["
    printf "%*s" $filled_length | tr ' ' '█'
    printf "%*s" $((bar_length - filled_length)) | tr ' ' '░'
    printf "] %d%% (%d/%d) - %s${NC}" $percentage $CURRENT_STEP $TOTAL_STEPS "$1"
    echo
}

# Funktion zum Validieren der IP-Adresse
validate_ip() {
    local ip=$1
    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        IFS='.' read -r -a octets <<< "$ip"
        for octet in "${octets[@]}"; do
            if [[ $octet -lt 0 || $octet -gt 255 ]]; then
                return 1
            fi
        done
        return 0
    fi
    return 1
}

# Funktion zum Validieren des Hostnames
validate_hostname() {
    local hostname=$1
    if [[ $hostname =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
        return 0
    fi
    return 1
}

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}     QR-Scanner & NFC-Kartenleser Installation      ${NC}"
echo -e "${BLUE}                   v2.1 - Erweitert               ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Überprüfen, ob das Skript als Root ausgeführt wird
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Bitte führen Sie das Skript als Root aus (sudo).${NC}"
    exit 1
fi

# Überprüfe ob auf Raspberry Pi ausgeführt
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null && ! grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Warnung: Dieses Skript ist für Raspberry Pi optimiert.${NC}"
    echo -e "${YELLOW}   Die Installation wird fortgesetzt, aber GPIO-Features könnten nicht funktionieren.${NC}"
    read -p "Möchten Sie trotzdem fortfahren? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Installation abgebrochen.${NC}"
        exit 1
    fi
fi

# Aktuelles Verzeichnis bestimmen
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# QR-Funktionalität Auswahl
echo -e "${PURPLE}====================================================${NC}"
echo -e "${PURPLE}           Konfiguration der QR-Funktionalität      ${NC}"
echo -e "${PURPLE}====================================================${NC}"
echo -e "${CYAN}Möchten Sie die QR/Barcode-Funktionalität aktivieren?${NC}"
echo -e "${YELLOW}Hinweis: Diese kann später über den sentrasupport-Account${NC}"
echo -e "${YELLOW}         jederzeit aktiviert/deaktiviert werden.${NC}"
read -p "QR-Funktionalität aktivieren? (j/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    QR_ENABLED=true
    echo -e "${GREEN}✅ QR-Funktionalität wird aktiviert${NC}"
else
    QR_ENABLED=false
    echo -e "${YELLOW}⚠️ QR-Funktionalität wird deaktiviert${NC}"
fi

echo -e "${PURPLE}====================================================${NC}"
echo -e "${PURPLE}        Automatische Netzwerk-Konfiguration        ${NC}"
echo -e "${PURPLE}====================================================${NC}"

# Automatische Konfiguration - DHCP standardmäßig verwenden
echo -e "${CYAN}Netzwerk-Einstellungen werden automatisch konfiguriert...${NC}"
NEW_HOSTNAME="guard-pi-$(date +%s | tail -c 5)"
echo -e "${GREEN}✅ Hostname wird automatisch gesetzt: $NEW_HOSTNAME${NC}"
echo -e "${GREEN}✅ DHCP wird verwendet (automatische IP-Zuweisung)${NC}"
echo -e "${YELLOW}   IP-Adresse wird vom Netzwerk automatisch zugewiesen${NC}"

# Statische IP auf false setzen für DHCP
CONFIGURE_STATIC_IP=false

# Dieser Block wird übersprungen, da wir automatisch DHCP verwenden
if false; then
    # Netzwerk-Interface ermitteln
    INTERFACE=$(ip route | grep default | head -n1 | awk '{print $5}')
    CURRENT_IP=$(hostname -I | awk '{print $1}')
    GATEWAY=$(ip route | grep default | head -n1 | awk '{print $3}')
    
    echo -e "${BLUE}Erkanntes Interface: $INTERFACE${NC}"
    echo -e "${BLUE}Aktuelle IP: $CURRENT_IP${NC}"
    echo -e "${BLUE}Gateway: $GATEWAY${NC}"
    echo
    
    # Statische IP eingeben
    while true; do
        read -p "Statische IP-Adresse eingeben (z.B. 192.168.1.100): " STATIC_IP
        if validate_ip "$STATIC_IP"; then
            break
        else
            echo -e "${RED}Ungültige IP-Adresse. Bitte im Format xxx.xxx.xxx.xxx eingeben.${NC}"
        fi
    done
    
    # Gateway eingeben
    while true; do
        read -p "Gateway eingeben (Standard: $GATEWAY): " STATIC_GATEWAY
        if [[ -z "$STATIC_GATEWAY" ]]; then
            STATIC_GATEWAY=$GATEWAY
            break
        elif validate_ip "$STATIC_GATEWAY"; then
            break
        else
            echo -e "${RED}Ungültige Gateway-Adresse.${NC}"
        fi
    done
    
    # DNS eingeben
    read -p "DNS-Server eingeben (Standard: 8.8.8.8): " DNS_SERVER
    if [[ -z "$DNS_SERVER" ]]; then
        DNS_SERVER="8.8.8.8"
    fi
    
    CONFIGURE_STATIC_IP=true
else
    CONFIGURE_STATIC_IP=false
fi

echo -e "${PURPLE}====================================================${NC}"
echo -e "${PURPLE}              Installation wird gestartet           ${NC}"
echo -e "${PURPLE}====================================================${NC}"

# Schritt 1: System aktualisieren
show_progress "System wird aktualisiert"
apt-get update > /dev/null 2>&1 || {
    echo -e "${RED}❌ Fehler beim Aktualisieren der Paketquellen${NC}"
    exit 1
}

apt-get upgrade -y > /dev/null 2>&1 || {
    echo -e "${RED}❌ Fehler beim System-Upgrade${NC}"
    exit 1
}

# Schritt 2: Erforderliche Pakete installieren
show_progress "Grundlegende Pakete werden installiert"
apt-get install -y python3 python3-pip python3-venv python3-dev python3-rpi.gpio \
                    sqlite3 nginx git libevdev-dev libudev-dev \
                    python3-libevdev evtest pcscd libpcsclite-dev swig curl wget \
                    htop vim build-essential python3-setuptools \
                    openssl dhcpcd5 > /dev/null 2>&1 || {
    echo -e "${RED}❌ Fehler bei der Paketinstallation${NC}"
    exit 1
}

# NetworkManager deaktivieren, falls vorhanden (Konflikt mit dhcpcd)
if systemctl is-active --quiet NetworkManager; then
    echo -e "${YELLOW}⚠️ NetworkManager wird deaktiviert (Konflikt mit dhcpcd)${NC}" >/dev/null || true
    systemctl stop NetworkManager 2>/dev/null || true
    systemctl disable NetworkManager 2>/dev/null || true
fi

# Schritt 3: Hostname konfigurieren
show_progress "Hostname wird konfiguriert"
if [[ "$NEW_HOSTNAME" != "$(hostname)" ]]; then
    # Hostname in /etc/hostname setzen
    echo "$NEW_HOSTNAME" > /etc/hostname
    
    # /etc/hosts backup und aktualisieren
    cp /etc/hosts /etc/hosts.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null
    
    # Entferne alte 127.0.1.1 Einträge und füge neuen hinzu
    sed -i '/127\.0\.1\.1/d' /etc/hosts
    echo -e "127.0.1.1\t$NEW_HOSTNAME" >> /etc/hosts
    
    # Hostname sofort setzen (ohne Neustart)
    hostnamectl set-hostname "$NEW_HOSTNAME"
    
    # Überprüfe ob Änderung erfolgreich
    if [[ "$(hostname)" == "$NEW_HOSTNAME" ]]; then
        echo -e "${GREEN}✅ Hostname erfolgreich geändert zu: $NEW_HOSTNAME${NC}" >/dev/null || true
        # SSL-Zertifikat muss neu generiert werden für neuen Hostname
        if [ -f "/etc/ssl/guard/guard.crt" ]; then
            echo -e "${YELLOW}⚠️ SSL-Zertifikat muss für neuen Hostname neu generiert werden${NC}" >/dev/null || true
            rm -f /etc/ssl/guard/guard.*
            rm -f nginx_ssl_config.conf
        fi
    fi
fi

# Schritt 4: Statische IP vorbereiten (SSH-sicher)
show_progress "Netzwerk wird vorbereitet"
if [[ "$CONFIGURE_STATIC_IP" == true ]]; then
    echo -e "${YELLOW}⚠️ IP-Änderung wird erst am Ende aktiviert (SSH-Schutz)${NC}" >/dev/null || true
    
    # Erkenne Netzwerk-Manager
    if systemctl is-active --quiet NetworkManager; then
        echo -e "${BLUE}NetworkManager erkannt - bereite statische IP vor...${NC}" >/dev/null || true
        
        # Alte guard-static Verbindung löschen falls vorhanden
        nmcli connection delete "guard-static" 2>/dev/null || true
        
        # NetworkManager-Verbindung für statische IP erstellen (aber NICHT aktivieren)
        nmcli connection add type ethernet con-name "guard-static" ifname "$INTERFACE" \
            ip4 "$STATIC_IP/24" gw4 "$STATIC_GATEWAY" ipv4.dns "$DNS_SERVER" \
            ipv4.method manual autoconnect no > /dev/null 2>&1
        
        NETWORK_METHOD="networkmanager"
        echo -e "${GREEN}✅ Statische IP-Konfiguration $STATIC_IP vorbereitet (NetworkManager)${NC}" >/dev/null || true
        
    elif systemctl is-active --quiet systemd-networkd; then
        echo -e "${BLUE}systemd-networkd erkannt - bereite statische IP vor...${NC}" >/dev/null || true
        
        # systemd-networkd Konfiguration erstellen
        cat > "/etc/systemd/network/20-guard-$INTERFACE.network" << EOF
[Match]
Name=$INTERFACE

[Network]
Address=$STATIC_IP/24
Gateway=$STATIC_GATEWAY
DNS=$DNS_SERVER
EOF
        
        NETWORK_METHOD="systemd-networkd"
        echo -e "${GREEN}✅ Statische IP-Konfiguration $STATIC_IP vorbereitet (systemd-networkd)${NC}" >/dev/null || true
        
    else
        echo -e "${BLUE}Installiere dhcpcd für Netzwerk-Konfiguration...${NC}" >/dev/null || true
        apt-get install -y dhcpcd5 > /dev/null 2>&1
        
        # dhcpcd Konfiguration vorbereiten
        if [[ -f "/etc/dhcpcd.conf" ]]; then
            cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null
        else
            touch /etc/dhcpcd.conf
        fi
        
        # Entferne alte Guard-Konfiguration
        sed -i '/# Statische IP-Konfiguration für.*SentraAI Entrance System/,+4d' /etc/dhcpcd.conf 2>/dev/null || true
        
        cat >> /etc/dhcpcd.conf << EOF

# Statische IP-Konfiguration für $INTERFACE - SentraAI Entrance System
interface $INTERFACE
static ip_address=$STATIC_IP/24
static routers=$STATIC_GATEWAY
static domain_name_servers=$DNS_SERVER
EOF
        
        systemctl enable dhcpcd > /dev/null 2>&1
        NETWORK_METHOD="dhcpcd"
        echo -e "${GREEN}✅ Statische IP-Konfiguration $STATIC_IP vorbereitet (dhcpcd)${NC}" >/dev/null || true
    fi
fi

# Schritt 5: Python-Umgebung erstellen
show_progress "Python-Umgebung wird erstellt"
if [ ! -d "venv" ]; then
    python3 -m venv venv > /dev/null 2>&1
else
    echo -e "${BLUE}Virtuelle Umgebung existiert bereits.${NC}"
fi

# Schritt 6: Python-Abhängigkeiten installieren
show_progress "Python-Abhängigkeiten werden installiert"
source venv/bin/activate
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# Installiere evdev mit System-Dependencies zuerst
echo -e "${BLUE}Installiere Hardware-Dependencies...${NC}"
pip install evdev > /dev/null 2>&1 || {
    echo -e "${YELLOW}⚠️ evdev Installation fehlgeschlagen - Hardware-Scanner könnten nicht funktionieren${NC}"
}

# Überprüfe ob requirements.txt existiert, ansonsten installiere einzeln
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
    # Installiere sd-notify für systemd watchdog
    pip install sd-notify > /dev/null 2>&1
else
    # Installiere alle erforderlichen Pakete für das Fallback-Logging-System
    pip install flask werkzeug waitress gunicorn pyscard requests psutil gpiozero lgpio jinja2 pytz sd-notify > /dev/null 2>&1
fi

# HINZUGEFÜGT: Pi 5 spezifische GPIO-Bibliotheken installieren
echo -e "${BLUE}Installiere Raspberry Pi 5 GPIO-Unterstützung...${NC}"
pip install lgpio gpiozero > /dev/null 2>&1 || {
    echo -e "${YELLOW}⚠️ lgpio Installation fehlgeschlagen - GPIO funktioniert möglicherweise nicht auf Pi 5${NC}"
}

# Schritt 7: Verzeichnisstruktur erstellen
show_progress "Verzeichnisstruktur wird erstellt"
mkdir -p data
mkdir -p logs
mkdir -p app/static/js
mkdir -p app/templates
mkdir -p backups

# Erstelle erweiterte Fallback-Logging-Verzeichnisse und Datenbanken
echo -e "${BLUE}Initialisiere erweitertes Fallback-Logging-System...${NC}"
touch data/fallback_log.sqlite
touch data/nfc_raw_data_analysis.db
chmod 666 data/fallback_log.sqlite
chmod 666 data/nfc_raw_data_analysis.db

# WICHTIG: Setze festen PASSWORD_SALT für konsistente admin/admin Anmeldung
echo -e "${BLUE}Konfiguriere Authentifizierungssystem...${NC}"
export AIQR_PASSWORD_SALT='aiqr_guard_v3_2025_fixed_salt_do_not_change'

# Bei Neuinstallation: Lösche users.json, damit admin/admin neu erstellt wird
if [ ! -f ".installed" ]; then
    echo -e "${YELLOW}Neuinstallation erkannt - Resette Benutzerdatenbank...${NC}"
    rm -f data/users.json
    rm -f data/door_control.json
    # Markiere als installiert für zukünftige Updates
    touch .installed
fi

# Schritt 8: Berechtigungen setzen
show_progress "Berechtigungen werden gesetzt"
chown -R root:root "$SCRIPT_DIR"
chmod -R 755 "$SCRIPT_DIR"
# Spezielle Berechtigungen für schreibbare Verzeichnisse
chmod -R 777 "$SCRIPT_DIR/data"
chmod -R 777 "$SCRIPT_DIR/logs"
chmod -R 755 "$SCRIPT_DIR/backups"

# Schritt 9: Hardware-Konfiguration
show_progress "Hardware-Zugriff wird konfiguriert"
# Berechtigungen für die udev-Regeln
cat > /etc/udev/rules.d/99-barcodescanner.rules << EOF
SUBSYSTEM=="input", GROUP="input", MODE="0666"
KERNEL=="event*", NAME="input/%k", MODE="0666"
EOF

# Stelle die udev-Regeln für NFC-Kartenleser ein
cat > /etc/udev/rules.d/99-nfcreader.rules << EOF
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", GROUP="dialout", MODE="0666", SYMLINK+="nfc"
SUBSYSTEM=="usb", ATTRS{idVendor}=="072f", ATTRS{idProduct}=="2200", GROUP="dialout", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="04e6", ATTRS{idProduct}=="5816", GROUP="dialout", MODE="0666"
EOF

# udev-Regeln neu laden
udevadm control --reload-rules > /dev/null 2>&1
udevadm trigger > /dev/null 2>&1

# Schritt 10: PC/SC-Service konfigurieren
show_progress "NFC-Service wird konfiguriert"
systemctl enable pcscd > /dev/null 2>&1
systemctl start pcscd > /dev/null 2>&1

# Schritt 11: Systemd-Service erstellen
show_progress "System-Service wird erstellt"
cat > /etc/systemd/system/qrverification.service << EOF
[Unit]
Description=QR Code & NFC Card Verification Service - Guard System
After=network.target pcscd.service
Wants=pcscd.service

[Service]
User=root
Group=root
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=$SCRIPT_DIR"
Environment="HOSTNAME=$NEW_HOSTNAME"
Environment="AIQR_PASSWORD_SALT=aiqr_guard_v3_2025_fixed_salt_do_not_change"
ExecStart=$SCRIPT_DIR/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 1 --worker-class sync --timeout 60 --log-level info wsgi:app
Restart=always
RestartSec=10
Type=simple
KillMode=mixed
KillSignal=SIGINT
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

# Schritt 12: Nginx konfigurieren
show_progress "Webserver wird konfiguriert"
cat > /etc/nginx/sites-available/qrverification << EOF
server {
    listen 80;
    server_name $NEW_HOSTNAME localhost _;

    # Erhöhe die maximale Upload-Größe für CSV-Dateien
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    # Statische Dateien direkt servieren
    location /static/ {
        alias $SCRIPT_DIR/app/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # Gzip-Kompression aktivieren
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
EOF

# Aktiviere die Nginx-Konfiguration
ln -sf /etc/nginx/sites-available/qrverification /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Schritt 13: Datenbank-Dateien erstellen
show_progress "Datenbank-Dateien werden erstellt"
# Erstelle eine leere Barcode-Datenbank, falls noch nicht vorhanden
if [ ! -f "barcode_database.txt" ]; then
    touch barcode_database.txt
    chmod 666 barcode_database.txt
fi

# Erstelle eine leere Permanente-Barcodes-Datei, falls noch nicht vorhanden
if [ ! -f "permanent_barcodes.txt" ]; then
    touch permanent_barcodes.txt
    chmod 666 permanent_barcodes.txt
fi

# Log-Datei erstellen
if [ ! -f "logs/app.log" ]; then
    touch logs/app.log
    chmod 666 logs/app.log
fi

# Schritt 14: SSL-Zertifikat automatisch generieren
show_progress "SSL-Zertifikat wird automatisch erstellt"
echo -e "${CYAN}SSL-Zertifikat wird automatisch generiert...${NC}"
# SSL automatisch aktivieren
if true; then
    echo -e "${YELLOW}SSL-Zertifikate werden generiert...${NC}"
    
    # OpenSSL installieren falls nicht vorhanden
    if ! command -v openssl &> /dev/null; then
        echo -e "${BLUE}Installiere OpenSSL...${NC}"
        apt-get install -y openssl > /dev/null 2>&1
    fi
    
    # SSL-Generator-Script ausführen falls vorhanden
    if [ -f "generate_ssl.sh" ]; then
        chmod +x generate_ssl.sh
        ./generate_ssl.sh
        
        # SSL-Nginx-Konfiguration aktivieren falls vorhanden
        if [ -f "nginx_ssl_config.conf" ] && [ -f "/etc/ssl/guard/guard.crt" ]; then
            echo -e "${GREEN}SSL-Zertifikat gefunden. SSL-Konfiguration wird aktiviert...${NC}"
            cp nginx_ssl_config.conf /etc/nginx/sites-available/qrverification_ssl
            ln -sf /etc/nginx/sites-available/qrverification_ssl /etc/nginx/sites-enabled/
            # Deaktiviere HTTP-only Konfiguration
            rm -f /etc/nginx/sites-enabled/qrverification
            SSL_ENABLED=true
        else
            echo -e "${YELLOW}⚠️ SSL-Zertifikat nicht gefunden. HTTP-Konfiguration wird verwendet.${NC}"
            SSL_ENABLED=false
        fi
    else
        echo -e "${YELLOW}⚠️ SSL-Generator nicht gefunden. HTTP-Konfiguration wird verwendet.${NC}"
        SSL_ENABLED=false
    fi
else
    SSL_ENABLED=false
fi

# Schritt 15: QR-Konfiguration in config.json setzen
show_progress "QR-Einstellung wird konfiguriert"

# Erstelle oder update config.json mit QR-Einstellung
if [ ! -f "config.json" ]; then
    echo '{
  "username": "admin",
  "password": "admin",
  "door_open_time": 1.5,
  "allow_all_barcodes": false,
  "nfc_webhook_url": "",
  "barcode_webhook_url": "",
  "webhook_enabled": true,
  "webhook_timeout": 5,
  "webhook_auth_user": "",
  "webhook_auth_password": "",
  "webhook_auth_type": "digest",
  "nfc_webhook_delay": 0.0,
  "barcode_webhook_delay": 0.0,
  "barcode_visibility_enabled": '$(if [ "$QR_ENABLED" = true ]; then echo "true"; else echo "false"; fi)'
}' > config.json
    echo -e "${GREEN}✅ Konfigurationsdatei erstellt mit QR-Einstellung${NC}"
else
    # Update existing config.json
    python3 -c "
import json
try:
    with open('config.json', 'r') as f:
        data = json.load(f)
except:
    data = {}

data['barcode_visibility_enabled'] = $( [ "$QR_ENABLED" = true ] && echo "True" || echo "False" )
if 'username' not in data:
    data['username'] = 'admin'
if 'password' not in data:
    data['password'] = 'admin'

with open('config.json', 'w') as f:
    json.dump(data, f, indent=2)
"
    echo -e "${GREEN}✅ QR-Einstellung in Konfiguration aktualisiert${NC}"
fi

# Schritt 16: Services starten
show_progress "Services werden gestartet"
# Test der Nginx-Konfiguration
nginx -t > /dev/null 2>&1

if [ $? -eq 0 ]; then
    # Aktiviere und starte Dienste
    systemctl daemon-reload > /dev/null 2>&1
    systemctl enable qrverification > /dev/null 2>&1
    systemctl restart qrverification > /dev/null 2>&1
    systemctl restart nginx > /dev/null 2>&1
    
    # Warte auf Service-Start
    sleep 3
else
    echo -e "${RED}❌ Fehler in der NGINX-Konfiguration.${NC}"
    nginx -t
    exit 1
fi

# Schritt 17: System-Tests und Validierung
show_progress "Erweiterte System-Tests werden durchgeführt"

# Integration Test ausführen
cat > integration_test.py << 'PYTHON_TEST_EOF'
import time
import sys
import os
import sqlite3
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test Legacy Fallback-Logging-System
try:
    from app import error_logger
    test_data = "test_data_123"
    error_logger.log_fallback(test_data, "installation_test")
    logs = error_logger.get_fallback_logs(limit=1)
    if logs and len(logs) > 0:
        print('✅ Legacy Fallback-Logging-System erfolgreich')
    else:
        print('⚠️ Legacy Fallback-Logging-System: Keine Test-Logs gefunden')
except Exception as e:
    print(f'⚠️ Legacy Fallback-Logging-System: {e}')

# Test Enhanced NFC Raw Data Analyzer
try:
    from app.models.nfc_raw_data_analyzer import nfc_raw_data_analyzer
    # Test Datenbank-Initialisierung
    test_cards = nfc_raw_data_analyzer.get_all_cards(limit=1)
    print('✅ Enhanced NFC Raw Data Analyzer erfolgreich')
except Exception as e:
    print(f'⚠️ Enhanced NFC Raw Data Analyzer: {e}')

# Test SQLite-Datenbanken
try:
    # Test Legacy Fallback-Datenbank
    conn1 = sqlite3.connect('data/fallback_log.sqlite')
    cursor1 = conn1.cursor()
    cursor1.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count1 = cursor1.fetchone()[0]
    conn1.close()
    
    # Test Enhanced NFC-Datenbank
    conn2 = sqlite3.connect('data/nfc_raw_data_analysis.db')
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count2 = cursor2.fetchone()[0]
    conn2.close()
    
    if table_count1 > 0 and table_count2 > 0:
        print('✅ Beide SQLite-Datenbanken erfolgreich')
    elif table_count1 > 0:
        print('✅ Legacy SQLite-Datenbank erfolgreich')
        print('ℹ️ Enhanced NFC-Datenbank wird bei erstem Scan initialisiert')
    else:
        print('⚠️ SQLite-Datenbanken: Initialisierung ausstehend')
except Exception as e:
    print(f'⚠️ SQLite-Datenbanken: {e}')

try:
    from app.gpio_control import pulse, get_gpio_state
    print('GPIO-Test läuft...')
    initial_state = get_gpio_state()
    pulse()
    time.sleep(0.1)
    final_state = get_gpio_state()
    print('✅ GPIO-Test erfolgreich')
except Exception as e:
    print(f'⚠️ GPIO-Test: {e}')
    
# Test Netzwerk-Konnektivität und neue vereinheitlichte Seiten
try:
    import requests
    # Test Hauptseite
    response = requests.get('http://localhost', timeout=5)
    if response.status_code == 200:
        print('✅ Webserver-Hauptseite erfolgreich')
    else:
        print(f'⚠️ Webserver-Hauptseite: Status {response.status_code}')
    
    # Test vereinheitlichtes Karten-Log
    response_log = requests.get('http://localhost/fallback-log', timeout=5)
    if response_log.status_code == 200:
        print('✅ Vereinheitlichtes Karten-Log erfolgreich')
    else:
        print(f'⚠️ Karten-Log: Status {response_log.status_code}')
        
except Exception as e:
    print(f'⚠️ Webserver-Test: {e}')

# Test evdev (Hardware-Scanner)
try:
    import evdev
    devices = evdev.list_devices()
    print(f'✅ evdev erfolgreich - {len(devices)} Geräte gefunden')
except Exception as e:
    print(f'⚠️ evdev: {e}')
PYTHON_TEST_EOF

source venv/bin/activate
python3 integration_test.py 2>/dev/null
rm -f integration_test.py

# Backup-Script erstellen
cat > backup_system.sh << 'EOF'
#!/bin/bash
# Automatisches Backup-Script für SentraAI Entrance System v3.0
# Erweitert für vereinheitlichtes Karten-Log-System
BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="guard_backup_$DATE.tar.gz"

echo "🔄 Erstelle erweitertes System-Backup: $BACKUP_FILE"
echo "📊 Erfasste Datenbanken:"
echo "   • Legacy Fallback-Log: data/fallback_log.sqlite"
echo "   • Enhanced NFC-Analyse: data/nfc_raw_data_analysis.db"

tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
    --exclude='venv' \
    --exclude='logs/*.log' \
    --exclude='backups' \
    --exclude='__pycache__' \
    .

# Überprüfe Backup-Integrität
if [ -f "$BACKUP_DIR/$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
    echo "✅ Backup erstellt: $BACKUP_DIR/$BACKUP_FILE ($BACKUP_SIZE)"
    
    # Test-Extraktion für Validierung
    tar -tzf "$BACKUP_DIR/$BACKUP_FILE" data/fallback_log.sqlite >/dev/null 2>&1 && \
    tar -tzf "$BACKUP_DIR/$BACKUP_FILE" data/nfc_raw_data_analysis.db >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ Backup-Integrität validiert - Beide Datenbanken enthalten"
    else
        echo "⚠️ Backup erstellt, aber Datenbank-Validierung fehlgeschlagen"
    fi
else
    echo "❌ Fehler beim Erstellen des Backups"
    exit 1
fi

# Alte Backups löschen (älter als 30 Tage)
DELETED_COUNT=$(find "$BACKUP_DIR" -name "guard_backup_*.tar.gz" -mtime +30 -delete -print 2>/dev/null | wc -l)
if [ $DELETED_COUNT -gt 0 ]; then
    echo "🗑️ $DELETED_COUNT alte Backups gelöscht (älter als 30 Tage)"
fi
EOF

chmod +x backup_system.sh

# NFC Kartenanalyse-Tool ausführbar machen
if [ -f "kartentest.py" ]; then
    chmod +x kartentest.py
    echo -e "${GREEN}✅ NFC Kartenanalyse-Tool (kartentest.py) aktiviert${NC}"
fi

echo
echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}     🎉 Installation erfolgreich abgeschlossen! 🎉  ${NC}"
echo -e "${GREEN}====================================================${NC}"

# Service-Status überprüfen
if systemctl is-active --quiet qrverification.service; then
    echo -e "${GREEN}✅ Alle Services laufen erfolgreich!${NC}"
    
    # IP-Adresse für Zugriff ermitteln
    if [[ "$CONFIGURE_STATIC_IP" == true ]]; then
        ACCESS_IP=$STATIC_IP
    else
        ACCESS_IP=$(hostname -I | awk '{print $1}')
    fi
    
    echo -e "${BLUE}📱 Die Anwendung ist jetzt erreichbar unter:${NC}"
    if [[ "$SSL_ENABLED" == true ]]; then
        echo -e "${BLUE}   • https://localhost${NC}"
        echo -e "${BLUE}   • https://$ACCESS_IP${NC}"
        echo -e "${BLUE}   • https://$NEW_HOSTNAME.local${NC}"
        echo -e "${GREEN}   🔒 SSL/HTTPS aktiviert${NC}"
    else
        echo -e "${BLUE}   • http://localhost${NC}"
        echo -e "${BLUE}   • http://$ACCESS_IP${NC}"
        echo -e "${BLUE}   • http://$NEW_HOSTNAME.local${NC}"
    fi
    echo
    echo -e "${BLUE}📋 Standard-Anmeldedaten:${NC}"
    echo -e "${BLUE}   • Benutzername: admin${NC}"
    echo -e "${BLUE}   • Passwort: admin${NC}"
    echo
    echo -e "${CYAN}🔧 System-Informationen:${NC}"
    echo -e "${CYAN}   • Hostname: $NEW_HOSTNAME${NC}"
    if [[ "$CONFIGURE_STATIC_IP" == true ]]; then
        echo -e "${CYAN}   • Statische IP: $STATIC_IP${NC}"
        echo -e "${CYAN}   • Gateway: $STATIC_GATEWAY${NC}"
    else
        echo -e "${CYAN}   • IP-Adresse: $ACCESS_IP (DHCP)${NC}"
    fi
    echo
    echo -e "${PURPLE}🛠️  Nützliche Kommandos:${NC}"
    echo -e "${PURPLE}   • Service-Status: sudo systemctl status qrverification${NC}"
    echo -e "${PURPLE}   • Service neustarten: sudo systemctl restart qrverification${NC}"
    echo -e "${PURPLE}   • Logs anzeigen: sudo journalctl -u qrverification -f${NC}"
    echo -e "${PURPLE}   • Backup erstellen: ./backup_system.sh${NC}"
    echo -e "${PURPLE}   • NFC-Kartenanalyse: sudo python3 kartentest.py${NC}"
    echo
    echo -e "${YELLOW}⚠️  Wichtige Hinweise:${NC}"
    if [[ "$CONFIGURE_STATIC_IP" == true ]]; then
        echo -e "${YELLOW}   • System wird neu gestartet, um Netzwerk-Änderungen zu aktivieren${NC}"
        echo -e "${YELLOW}   • Nach dem Neustart ist das System unter der neuen IP erreichbar${NC}"
    fi
    if [[ "$SSL_ENABLED" == true ]]; then
        echo -e "${YELLOW}   • Bei Self-Signed Zertifikaten: Sicherheitswarnung im Browser akzeptieren${NC}"
        echo -e "${YELLOW}   • Für Produktionsumgebung: Zertifikat durch CA-signiertes ersetzen${NC}"
    fi
    echo -e "${YELLOW}   • Bitte ändern Sie das Standard-Passwort nach der ersten Anmeldung${NC}"
    echo -e "${YELLOW}   • Regelmäßige Backups werden empfohlen (./backup_system.sh)${NC}"
    echo -e "${YELLOW}   • Vereinfachtes System ohne komplexe Sicherheitsfeatures${NC}"
    echo -e "${YELLOW}   • Dashboard aktualisiert sich automatisch über AJAX${NC}"
    echo -e "${YELLOW}   • Neues vereinheitlichtes Karten-Log mit NFC-Analyse integriert${NC}"
    echo -e "${YELLOW}   • Enhanced NFC Raw Data Analyzer für Patch-Entwicklung${NC}"
    echo
    echo -e "${GREEN}====================================================${NC}"
    
    # Intelligente IP-Aktivierung als letzter Schritt
    if [[ "$CONFIGURE_STATIC_IP" == true ]] && [[ ! -z "$STATIC_IP" ]]; then
        echo
        echo -e "${RED}============================================${NC}"
        echo -e "${RED}   🚨 KRITISCHER SCHRITT: IP-AKTIVIERUNG   ${NC}"
        echo -e "${RED}============================================${NC}"
        echo -e "${YELLOW}Die statische IP $STATIC_IP wird jetzt aktiviert.${NC}"
        echo -e "${RED}⚠️ WARNUNG: SSH-Verbindung wird unterbrochen!${NC}"
        echo -e "${YELLOW}Nach der Aktivierung erreichen Sie das System unter:${NC}"
        if [[ "$SSL_ENABLED" == true ]]; then
            echo -e "${CYAN}   • https://$STATIC_IP${NC}"
            echo -e "${CYAN}   • https://$NEW_HOSTNAME.local${NC}"
        else
            echo -e "${CYAN}   • http://$STATIC_IP${NC}"
            echo -e "${CYAN}   • http://$NEW_HOSTNAME.local${NC}"
        fi
        echo
        echo -e "${YELLOW}Möchten Sie die IP-Adresse JETZT aktivieren?${NC}"
        echo -e "${YELLOW}(Alternative: IP wird beim nächsten Neustart aktiviert)${NC}"
        read -p "IP JETZT aktivieren? (y/N): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}🔄 Aktiviere statische IP - SSH wird unterbrochen...${NC}"
            sleep 2
            
            if [[ "$NETWORK_METHOD" == "networkmanager" ]]; then
                # NetworkManager: Verbindung wechseln
                CURRENT_CON=$(nmcli -t -f NAME,DEVICE connection show --active | grep "$INTERFACE" | cut -d: -f1)
                if [[ ! -z "$CURRENT_CON" ]] && [[ "$CURRENT_CON" != "guard-static" ]]; then
                    echo -e "${YELLOW}Wechsle von '$CURRENT_CON' zu 'guard-static'...${NC}"
                    nmcli connection down "$CURRENT_CON" && nmcli connection up "guard-static"
                else
                    nmcli connection up "guard-static"
                fi
            elif [[ "$NETWORK_METHOD" == "systemd-networkd" ]]; then
                # systemd-networkd: Service neustarten
                systemctl restart systemd-networkd
            elif [[ "$NETWORK_METHOD" == "dhcpcd" ]]; then
                # dhcpcd: Service neustarten
                systemctl restart dhcpcd
            fi
            
            echo -e "${GREEN}✅ Statische IP aktiviert${NC}"
            echo -e "${YELLOW}SSH-Verbindung wird in 5 Sekunden getrennt...${NC}"
            echo -e "${CYAN}Neue Verbindung: ssh $(whoami)@$STATIC_IP${NC}"
            sleep 5
            
        else
            echo -e "${YELLOW}✅ IP-Konfiguration vorbereitet${NC}"
            echo -e "${YELLOW}Statische IP wird beim nächsten Neustart aktiviert:${NC}"
            echo -e "${YELLOW}   sudo reboot${NC}"
            echo
            echo -e "${CYAN}Nach dem Neustart erreichbar unter:${NC}"
            if [[ "$SSL_ENABLED" == true ]]; then
                echo -e "${CYAN}   • https://$STATIC_IP${NC}"
                echo -e "${CYAN}   • https://$NEW_HOSTNAME.local${NC}"
            else
                echo -e "${CYAN}   • http://$STATIC_IP${NC}"
                echo -e "${CYAN}   • http://$NEW_HOSTNAME.local${NC}"
            fi
            echo -e "${YELLOW}Neue SSH-Verbindung: ssh $(whoami)@$STATIC_IP${NC}"
        fi
    fi
    
else
    echo -e "${RED}❌ Service läuft nicht. Fehlerdiagnose:${NC}"
    echo -e "${YELLOW}Service-Status:${NC}"
    systemctl status qrverification.service --no-pager -l
    echo
    echo -e "${YELLOW}Letzte Log-Einträge:${NC}"
    journalctl -u qrverification.service --no-pager -l | tail -10
fi