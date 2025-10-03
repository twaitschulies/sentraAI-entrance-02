# NFC Kartenanalyse-Tool v2.0

## Zweck
Umfassendes Analyse-Tool zur Diagnose von NFC-Kartenerkennungsproblemen, speziell optimiert für Visa und PayPal-Karten, die aktuell nicht erkannt werden.

## Features

### 🔍 Umfassende Datensammlung
- **ATR (Answer To Reset)** und historische Bytes
- **PSE/PPSE** (Payment System Environment) Erkennung
- **AID-Discovery** mit über 30 bekannten AIDs
- **EMV-Datenextraktion** (PAN, Ablaufdatum, Karteninhaber)
- **Rohdaten-Erfassung** aller APDU-Commands und Responses

### 🧪 Experimentelle Methoden
- Alternative SELECT-Command Varianten (P1/P2)
- Direkte TAG-Abfragen (GET DATA)
- SFI-Scanning (1-31) für versteckte Records
- PayPal/Wallet-spezifische AIDs
- Visa-spezifische Optimierungen (Credit/Debit/V PAY)
- CPLC (Card Production Life Cycle) Daten

### 📊 Ausgabe & Reporting
- JSON-Export für maschinelle Auswertung
- Human-readable Textreport
- Kartenvergleich-Funktion
- Timing-Analyse pro APDU-Command
- Fehlerprotokollierung mit Debug-Log

## Installation

```bash
# Auf Raspberry Pi 4b:
sudo ./install.sh
# Das Tool wird automatisch ausführbar gemacht
```

## Verwendung

### Interaktiver Modus (Empfohlen)
```bash
sudo python3 kartentest.py
```

Menüoptionen:
1. **Einzelne Karte testen** - Vollständige Analyse einer Karte
2. **Mehrere Karten testen** - Batch-Analyse mehrerer Karten
3. **Vergleich durchführen** - Unterschiede zwischen Karten finden
4. **Ergebnisse speichern** - JSON-Export
5. **Report generieren** - Textbericht erstellen
6. **Schnelltest** - Fokus auf Visa/PayPal-Probleme

### Schnelltest-Modus
```bash
# Für schnelle Visa/PayPal-Diagnose:
sudo python3 kartentest.py --quick

# Mit spezifischem Kartennamen:
sudo python3 kartentest.py --quick --card "Visa Debit"

# Mit eigener Ausgabedatei:
sudo python3 kartentest.py --quick --output visa_test.json
```

## Ausgabeformat

### JSON-Struktur
```json
{
  "test_session": "2024-01-25T10:30:00",
  "card_tests": [{
    "card_name": "Visa Credit",
    "atr": "3B 65 00 ...",
    "aids_found": [
      {"type": "Visa", "aid": "A0000000031010", "fci": {...}}
    ],
    "emv_data": {
      "A0000000031010": {
        "pan": "4xxx****xxxx",
        "expiry": "12/28",
        "cardholder": "MAX MUSTERMANN"
      }
    },
    "raw_apdus": [{
      "command": "00 A4 04 00 07 A0 00 00 00 03 10 10",
      "response": "6F 2B 84 07 ...",
      "status": "9000",
      "time_ms": 45,
      "description": "SELECT Visa AID"
    }],
    "experimental_findings": {
      "visa_credit": {"found": true, "fci": "..."},
      "cplc": "9F7F2A..."
    },
    "errors": []
  }]
}
```

## Bekannte Probleme & Lösungen

### Problem: Visa-Karten werden nicht erkannt
**Lösung:** Das Tool testet automatisch alle 5 Visa-AID-Varianten:
- Visa Credit: `A0000000031010`
- Visa Debit: `A0000000032010`
- V PAY: `A0000000032020`
- Visa Plus: `A0000000038010`
- Visa Interlink: `A0000000039010`

### Problem: PayPal-Karten werden nicht erkannt
**Lösung:** Das Tool testet 3 bekannte PayPal-AIDs:
- Standard PayPal: `325041592E5359532E4444463031`
- Alternative: `A0000006510100`
- JCB/PayPal: `A0000000651010`

### Problem: Karte reagiert nicht auf Standard-Commands
**Lösung:** Das Tool verwendet automatisch:
- Alternative SELECT-Varianten (P1/P2)
- Verschiedene GPO-PDOLs
- Direkte TAG-Abfragen
- Experimentelles SFI-Scanning

## Analyse-Workflow

### 1. Datensammlung (3-5 Karten pro Typ)
```bash
sudo python3 kartentest.py
# Option 2: Mehrere Karten testen
# Testen Sie mindestens:
# - 3x funktionierende Karten (Mastercard/Maestro)
# - 3x nicht funktionierende Karten (Visa/PayPal)
```

### 2. Vergleich durchführen
```bash
# Im interaktiven Menü Option 3
# Vergleicht ATR, AIDs und gefundene Daten
```

### 3. Ergebnisse analysieren
```bash
# JSON-Datei öffnen und vergleichen:
cat data/kartentest_results_*.json | python3 -m json.tool | less

# Nach Unterschieden suchen:
grep -A5 "visa\|paypal" data/kartentest_results_*.json
```

### 4. NFC-Reader anpassen
Basierend auf den Ergebnissen, passen Sie `app/nfc_reader.py` an:
- Neue AIDs hinzufügen
- GPO-Parameter anpassen
- Timeout-Werte optimieren

## Debug-Modus

Für detaillierte APDU-Protokollierung:
```bash
# Debug-Log aktivieren
export NFC_DEBUG=true
sudo python3 kartentest.py

# Log-Datei analysieren
tail -f kartentest_debug.log
```

## Typische Fehlercodes

- `9000`: Erfolgreich
- `6A82`: Datei/Application nicht gefunden
- `6985`: Bedingungen nicht erfüllt
- `6D00`: Befehl nicht unterstützt
- `6E00`: Klasse nicht unterstützt
- `6700`: Falsche Länge

## Support

Bei Problemen:
1. Debug-Log aktivieren (`export NFC_DEBUG=true`)
2. Mindestens 5 Tests mit problematischen Karten durchführen
3. JSON-Ergebnisse und Debug-Log sichern
4. Issue auf GitHub mit Logs erstellen

## Sicherheitshinweise

⚠️ **Das Tool zeigt maskierte PANs an** (erste 6 und letzte 4 Ziffern)
⚠️ **Speichern Sie keine ungefilterten Kartendaten in öffentlichen Repositories**
⚠️ **Löschen Sie Testdaten nach der Analyse**

## Nächste Schritte

Nach erfolgreicher Analyse:

1. **Identifizieren Sie die fehlenden AIDs** für Visa/PayPal
2. **Vergleichen Sie GPO-Responses** zwischen funktionierenden und nicht funktionierenden Karten
3. **Passen Sie app/nfc_reader.py an** mit den neuen Erkenntnissen
4. **Testen Sie die Änderungen** mit dem echten System

## Lizenz

Teil des Guard NFC/QR v2 Systems - nur für Entwicklung und Diagnose.