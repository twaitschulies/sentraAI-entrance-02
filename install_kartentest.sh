#!/bin/bash

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}     NFC Kartentest Tool - Installation              ${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════${NC}\n"

# Prüfe ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Bitte als root ausführen: sudo ./install_kartentest.sh${NC}"
    exit 1
fi

# Schritt 1: System-Pakete installieren
echo -e "${YELLOW}📦 Installiere System-Pakete...${NC}"
apt-get update >/dev/null 2>&1
apt-get install -y pcscd libpcsclite-dev swig python3-dev python3-pip python3-venv >/dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ System-Pakete installiert${NC}"
else
    echo -e "${RED}❌ Fehler bei der Installation der System-Pakete${NC}"
    exit 1
fi

# Schritt 2: PCSC-Dienst starten
echo -e "${YELLOW}🔧 Starte PCSC-Dienst...${NC}"
systemctl enable pcscd >/dev/null 2>&1
systemctl start pcscd >/dev/null 2>&1

if systemctl is-active --quiet pcscd; then
    echo -e "${GREEN}✅ PCSC-Dienst läuft${NC}"
else
    echo -e "${RED}❌ PCSC-Dienst konnte nicht gestartet werden${NC}"
    exit 1
fi

# Schritt 3: Virtual Environment prüfen/erstellen
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_PATH="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}🐍 Erstelle Virtual Environment...${NC}"
    python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✅ Virtual Environment erstellt${NC}"
else
    echo -e "${GREEN}✅ Virtual Environment vorhanden${NC}"
fi

# Schritt 4: pyscard in venv installieren
echo -e "${YELLOW}📥 Installiere pyscard in Virtual Environment...${NC}"
source "$VENV_PATH/bin/activate"

# Upgrade pip
pip install --upgrade pip >/dev/null 2>&1

# Installiere pyscard
pip install pyscard >/dev/null 2>&1

if python3 -c "import smartcard" 2>/dev/null; then
    echo -e "${GREEN}✅ pyscard erfolgreich installiert${NC}"
else
    echo -e "${RED}❌ pyscard Installation fehlgeschlagen${NC}"
    echo -e "${YELLOW}Versuche alternative Installation...${NC}"

    # Alternative: Build from source
    pip install --no-cache-dir pyscard >/dev/null 2>&1

    if python3 -c "import smartcard" 2>/dev/null; then
        echo -e "${GREEN}✅ pyscard erfolgreich installiert (Alternative)${NC}"
    else
        echo -e "${RED}❌ pyscard konnte nicht installiert werden${NC}"
        exit 1
    fi
fi

# Schritt 5: Test der Installation
echo -e "${YELLOW}🔍 Teste NFC-Reader Verbindung...${NC}"

python3 -c "
from smartcard.System import readers
reader_list = readers()
if reader_list:
    print('✅ NFC-Reader gefunden:', reader_list[0])
else:
    print('⚠️ Kein NFC-Reader gefunden (normal wenn kein Reader angeschlossen)')
" 2>/dev/null

deactivate

# Schritt 6: Wrapper-Skript erstellen
echo -e "${YELLOW}📝 Erstelle Ausführungs-Wrapper...${NC}"

cat > "$SCRIPT_DIR/run_kartentest.sh" << 'EOF'
#!/bin/bash

# Aktiviere Virtual Environment und führe kartentest.py aus
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR/venv/bin/activate"

# Führe kartentest.py mit allen übergebenen Parametern aus
python3 "$SCRIPT_DIR/kartentest.py" "$@"

deactivate
EOF

chmod +x "$SCRIPT_DIR/run_kartentest.sh"
chmod +x "$SCRIPT_DIR/kartentest.py"

# Schritt 7: Systemweiter Link erstellen
if [ -f "/usr/local/bin/kartentest" ]; then
    rm /usr/local/bin/kartentest
fi
ln -s "$SCRIPT_DIR/run_kartentest.sh" /usr/local/bin/kartentest

echo -e "${GREEN}✅ Wrapper-Skript erstellt${NC}"

# Schritt 8: Erfolgsmeldung
echo
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}     ✅ Installation erfolgreich abgeschlossen!        ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo
echo -e "${BLUE}Verwendung:${NC}"
echo -e "  ${YELLOW}sudo kartentest${NC}              - Interaktiver Modus"
echo -e "  ${YELLOW}sudo kartentest --quick${NC}      - Schnelltest"
echo -e "  ${YELLOW}sudo kartentest --help${NC}       - Hilfe anzeigen"
echo
echo -e "${BLUE}Alternative (aus diesem Verzeichnis):${NC}"
echo -e "  ${YELLOW}sudo ./run_kartentest.sh${NC}"
echo
echo -e "${GREEN}Das Tool ist jetzt einsatzbereit!${NC}"
echo