#!/bin/bash

echo "🔧 Guard NFC QR System - Dependency Fix Script"
echo "==============================================="

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Aktuelles Verzeichnis prüfen
if [[ ! -f "wsgi.py" ]]; then
    echo -e "${RED}❌ Fehler: Bitte führen Sie das Skript im QRVerification-Verzeichnis aus${NC}"
    echo "cd /usr/local/bin/QRVerification"
    echo "./fix_dependencies.sh"
    exit 1
fi

echo -e "${YELLOW}🔍 Diagnose läuft...${NC}"

# 1. Permissions korrigieren
echo -e "${YELLOW}📁 Korrigiere Berechtigungen...${NC}"
sudo chmod -R 777 logs/ data/ 2>/dev/null || true
sudo chown -R $USER:$USER logs/ data/ 2>/dev/null || true
echo -e "${GREEN}✅ Berechtigungen korrigiert${NC}"

# 2. Python Dependencies installieren
echo -e "${YELLOW}🐍 Installiere Python Dependencies...${NC}"
source venv/bin/activate

# System-weite Installation falls venv nicht funktioniert
if ! pip list | grep -q flask; then
    echo -e "${YELLOW}   Installiere requirements.txt...${NC}"
    pip install -r requirements.txt
fi

# Wichtige Module einzeln prüfen und installieren  
REQUIRED_MODULES=("flask" "evdev" "werkzeug" "gunicorn" "pyscard" "requests" "psutil" "gpiozero")

for module in "${REQUIRED_MODULES[@]}"; do
    if ! pip list | grep -q "^$module "; then
        echo -e "${YELLOW}   Installiere $module...${NC}"
        pip install "$module"
    else
        echo -e "${GREEN}   ✅ $module bereits installiert${NC}"
    fi
done

# lgpio für Pi 5
echo -e "${YELLOW}   Installiere lgpio für Pi 5...${NC}"
pip install lgpio || echo -e "${YELLOW}   ⚠️ lgpio Installation optional fehlgeschlagen${NC}"

# 3. Test der Installation
echo -e "${YELLOW}🧪 Teste Installation...${NC}"
python3 -c "
try:
    import app
    print('✅ App-Import erfolgreich')
except Exception as e:
    print(f'❌ App-Import fehlgeschlagen: {e}')
    import traceback
    traceback.print_exc()
"

# 4. Service neu starten
echo -e "${YELLOW}🔄 Starte Services neu...${NC}"
sudo systemctl restart qrverification
sudo systemctl restart nginx

# 5. Status prüfen
echo -e "${YELLOW}📊 Status prüfen...${NC}"
sleep 3

if systemctl is-active --quiet qrverification; then
    echo -e "${GREEN}✅ qrverification Service läuft${NC}"
else
    echo -e "${RED}❌ qrverification Service läuft nicht${NC}"
    echo "Logs: sudo journalctl -u qrverification -n 20"
fi

if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✅ nginx Service läuft${NC}"
else
    echo -e "${RED}❌ nginx Service läuft nicht${NC}"
fi

# 6. Connectivity Test
echo -e "${YELLOW}🌐 Teste Webserver...${NC}"
if curl -s --max-time 5 http://127.0.0.1:8000 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend (Port 8000) erreichbar${NC}"
else
    echo -e "${RED}❌ Backend (Port 8000) nicht erreichbar${NC}"
fi

if curl -s --max-time 5 http://127.0.0.1 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend (Port 80) erreichbar${NC}"
    echo -e "${GREEN}🎉 WebGUI sollte funktionieren!${NC}"
    IP=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}📱 Zugriff: http://$IP${NC}"
    echo -e "${GREEN}👤 Login: admin / admin${NC}"
else
    echo -e "${RED}❌ Frontend (Port 80) nicht erreichbar${NC}"
    echo "Prüfen Sie: sudo systemctl status nginx"
fi

echo "==============================================="
echo -e "${GREEN}🔧 Fix-Script abgeschlossen${NC}"

deactivate 2>/dev/null || true 