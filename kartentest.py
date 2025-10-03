#!/usr/bin/env python3
"""
Umfassendes NFC-Kartenanalyse-Tool
Version 2.0 - Erweiterte Visa/PayPal-Erkennung
Optimiert für Raspberry Pi 4b mit ACR122U Reader
"""

import os
import sys
import json
import time
import logging
import argparse
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

try:
    from smartcard.System import readers
    from smartcard.util import toHexString, toBytes
    from smartcard.Exceptions import NoCardException, CardConnectionException
    from smartcard.scard import *
except ImportError:
    print("❌ pyscard nicht installiert! Bitte ausführen:")
    print("   sudo apt-get install pcscd libpcsclite-dev")
    print("   pip3 install pyscard")
    sys.exit(1)

# Farbige Ausgabe für bessere Übersicht
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kartentest_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CardTester:
    """Umfassende NFC-Karten-Analyse-Klasse"""

    def __init__(self):
        self.connection = None
        self.test_results = []
        self.current_test = {}
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Bekannte AIDs für verschiedene Kartentypen
        self.known_aids = {
            # Mastercard
            'Mastercard': ['A0000000041010', 'A0000000043060', 'A0000000046000'],
            'Maestro': ['A0000000043060', 'A0000000046000'],

            # Visa
            'Visa': ['A0000000031010', 'A0000000032010', 'A0000000032020',
                     'A0000000038010', 'A0000000039010'],
            'Visa Electron': ['A0000000032010', 'A0000000032020'],

            # German Cards
            'Girocard': ['A0000003591010028001', 'D27600002547410100',
                         'A0000000593101001101', 'A0000001211010',
                         'A0000000596545410'],

            # PayPal / Digital Wallets
            'PayPal': ['325041592E5359532E4444463031', 'A0000000651010'],

            # American Express
            'Amex': ['A00000002501', 'A000000025010402', 'A000000025010801'],

            # Other Payment Systems
            'UnionPay': ['A000000333010101', 'A000000333010102', 'A000000333010103'],
            'JCB': ['A0000000651010'],
            'Discover': ['A0000001523010', 'A0000003241010'],

            # EMV Test AIDs
            'EMV Test': ['A0000000421010', 'A0000000422010', 'A0000000423010']
        }

        # EMV-Tags für Datenextraktion
        self.emv_tags = {
            '5A': 'Primary Account Number (PAN)',
            '5F24': 'Application Expiration Date',
            '5F20': 'Cardholder Name',
            '5F28': 'Issuer Country Code',
            '5F2A': 'Transaction Currency Code',
            '5F34': 'Application PAN Sequence Number',
            '9F08': 'Application Version Number',
            '9F0D': 'Issuer Action Code - Default',
            '9F0E': 'Issuer Action Code - Denial',
            '9F0F': 'Issuer Action Code - Online',
            '9F10': 'Issuer Application Data',
            '9F11': 'Issuer Code Table Index',
            '9F12': 'Application Preferred Name',
            '9F13': 'Last Online ATC Register',
            '9F17': 'PIN Try Counter',
            '9F36': 'Application Transaction Counter',
            '9F4D': 'Log Entry',
            '9F4F': 'Log Format',
            '82': 'Application Interchange Profile',
            '84': 'Dedicated File (DF) Name',
            '87': 'Application Priority Indicator',
            '94': 'Application File Locator (AFL)',
            '95': 'Terminal Verification Results',
            '9A': 'Transaction Date',
            '9B': 'Transaction Status Information',
            '9C': 'Transaction Type',
            '9F02': 'Amount, Authorized',
            '9F03': 'Amount, Other',
            '9F26': 'Application Cryptogram',
            '9F27': 'Cryptogram Information Data',
            '9F37': 'Unpredictable Number'
        }

    def connect_to_reader(self, max_retries: int = 3) -> bool:
        """Verbindung zum NFC-Reader herstellen"""
        for attempt in range(max_retries):
            try:
                reader_list = readers()
                if not reader_list:
                    print(f"{Colors.FAIL}❌ Kein NFC-Reader gefunden{Colors.END}")
                    return False

                reader = reader_list[0]
                print(f"{Colors.GREEN}✅ Reader gefunden: {reader}{Colors.END}")

                print(f"{Colors.CYAN}Bitte Karte auflegen...{Colors.END}")
                self.connection = reader.createConnection()
                self.connection.connect()

                print(f"{Colors.GREEN}✅ Karte erkannt!{Colors.END}")
                return True

            except NoCardException:
                print(f"{Colors.WARNING}⏳ Warte auf Karte... (Versuch {attempt + 1}/{max_retries}){Colors.END}")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Verbindungsfehler: {e}")
                time.sleep(1)

        return False

    def send_apdu(self, apdu: List[int], description: str = "") -> Tuple[List[int], int, int]:
        """APDU-Befehl senden und Response loggen"""
        start_time = time.time()
        try:
            data, sw1, sw2 = self.connection.transmit(apdu)
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Logging für Debug
            apdu_hex = toHexString(apdu)
            response_hex = toHexString(data) if data else ""
            status = f"{sw1:02X}{sw2:02X}"

            # In current_test speichern
            if 'raw_apdus' not in self.current_test:
                self.current_test['raw_apdus'] = []

            self.current_test['raw_apdus'].append({
                'command': apdu_hex,
                'response': response_hex,
                'status': status,
                'time_ms': elapsed_ms,
                'description': description
            })

            if sw1 == 0x90 and sw2 == 0x00:
                logger.debug(f"✅ {description}: {status}")
            else:
                logger.debug(f"⚠️ {description}: {status}")

            return data, sw1, sw2

        except Exception as e:
            logger.error(f"APDU-Fehler bei '{description}': {e}")
            return [], 0x00, 0x00

    def get_atr(self) -> str:
        """ATR (Answer To Reset) auslesen"""
        try:
            atr = self.connection.getATR()
            atr_hex = toHexString(atr)
            self.current_test['atr'] = atr_hex
            print(f"{Colors.BLUE}ATR: {atr_hex}{Colors.END}")

            # Historische Bytes extrahieren
            if len(atr) > 4:
                hist_bytes = atr[4:]
                self.current_test['historical_bytes'] = toHexString(hist_bytes)

            return atr_hex
        except Exception as e:
            logger.error(f"ATR-Fehler: {e}")
            return ""

    def select_pse(self) -> bool:
        """PSE (Payment System Environment) auswählen"""
        # 1PAY.SYS.DDF01 für Kontakt
        pse_apdu = [0x00, 0xA4, 0x04, 0x00, 0x0E,
                    0x31, 0x50, 0x41, 0x59, 0x2E, 0x53, 0x59, 0x53, 0x2E,
                    0x44, 0x44, 0x46, 0x30, 0x31]

        data, sw1, sw2 = self.send_apdu(pse_apdu, "SELECT PSE (1PAY.SYS.DDF01)")

        if sw1 == 0x90 and sw2 == 0x00:
            print(f"{Colors.GREEN}✅ PSE gefunden{Colors.END}")
            self.parse_fci(data)
            return True

        # 2PAY.SYS.DDF01 für kontaktlos
        ppse_apdu = [0x00, 0xA4, 0x04, 0x00, 0x0E,
                     0x32, 0x50, 0x41, 0x59, 0x2E, 0x53, 0x59, 0x53, 0x2E,
                     0x44, 0x44, 0x46, 0x30, 0x31]

        data, sw1, sw2 = self.send_apdu(ppse_apdu, "SELECT PPSE (2PAY.SYS.DDF01)")

        if sw1 == 0x90 and sw2 == 0x00:
            print(f"{Colors.GREEN}✅ PPSE gefunden (kontaktlos){Colors.END}")
            self.parse_fci(data)
            return True

        return False

    def parse_fci(self, data: List[int]) -> Dict[str, Any]:
        """FCI (File Control Information) parsen"""
        try:
            fci_data = {}
            data_hex = bytes(data)

            # Einfaches TLV-Parsing
            i = 0
            while i < len(data_hex):
                if i + 1 >= len(data_hex):
                    break

                tag = data_hex[i]
                length = data_hex[i + 1] if i + 1 < len(data_hex) else 0

                if i + 2 + length <= len(data_hex):
                    value = data_hex[i + 2:i + 2 + length]

                    # Spezielle Tags behandeln
                    if tag == 0x84:  # DF Name (AID)
                        fci_data['aid'] = value.hex().upper()
                    elif tag == 0x50:  # Application Label
                        try:
                            fci_data['label'] = value.decode('ascii')
                        except:
                            fci_data['label'] = value.hex()
                    elif tag == 0x87:  # Application Priority
                        fci_data['priority'] = value[0] if value else 0

                i += 2 + length

            return fci_data

        except Exception as e:
            logger.error(f"FCI-Parse-Fehler: {e}")
            return {}

    def brute_force_aids(self) -> List[str]:
        """Alle bekannten AIDs durchprobieren"""
        found_aids = []
        print(f"\n{Colors.CYAN}🔍 Durchsuche bekannte AIDs...{Colors.END}")

        for card_type, aids in self.known_aids.items():
            for aid in aids:
                try:
                    aid_bytes = bytes.fromhex(aid)
                    apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)

                    data, sw1, sw2 = self.send_apdu(apdu, f"SELECT {card_type} AID")

                    if sw1 == 0x90 and sw2 == 0x00:
                        print(f"{Colors.GREEN}  ✅ {card_type}: {aid}{Colors.END}")
                        found_aids.append({
                            'type': card_type,
                            'aid': aid,
                            'fci': self.parse_fci(data)
                        })
                    elif sw1 == 0x6A and sw2 == 0x82:
                        # File not found - normal für nicht vorhandene AIDs
                        pass
                    else:
                        logger.debug(f"  {card_type} ({aid}): {sw1:02X}{sw2:02X}")

                except Exception as e:
                    logger.error(f"AID-Test-Fehler für {aid}: {e}")

        self.current_test['aids_found'] = found_aids
        return found_aids

    def get_processing_options(self, aid: str) -> Optional[List[int]]:
        """GET PROCESSING OPTIONS für eine AID ausführen"""
        try:
            # Standard GPO mit leerem PDOL
            gpo_apdu = [0x80, 0xA8, 0x00, 0x00, 0x02, 0x83, 0x00]
            data, sw1, sw2 = self.send_apdu(gpo_apdu, f"GPO für {aid}")

            if sw1 == 0x90 and sw2 == 0x00:
                return data

            # Alternative GPO-Varianten probieren
            variants = [
                [0x80, 0xA8, 0x00, 0x00, 0x00],  # Ohne Daten
                [0x80, 0xA8, 0x00, 0x00, 0x04, 0x83, 0x02, 0x00, 0x00],  # Mit Amount
            ]

            for variant in variants:
                data, sw1, sw2 = self.send_apdu(variant, f"GPO Variante für {aid}")
                if sw1 == 0x90 and sw2 == 0x00:
                    return data

        except Exception as e:
            logger.error(f"GPO-Fehler: {e}")

        return None

    def read_record(self, sfi: int, record_num: int) -> Optional[List[int]]:
        """Record aus einer SFI lesen"""
        p2 = (sfi << 3) | 0x04
        apdu = [0x00, 0xB2, record_num, p2, 0x00]

        data, sw1, sw2 = self.send_apdu(apdu, f"READ RECORD SFI={sfi} Record={record_num}")

        if sw1 == 0x90 and sw2 == 0x00:
            return data
        return None

    def extract_emv_data(self, aid_info: Dict[str, Any]) -> Dict[str, Any]:
        """EMV-Daten für eine spezifische AID extrahieren"""
        emv_data = {}
        aid = aid_info.get('aid', '')

        print(f"\n{Colors.CYAN}📊 Extrahiere EMV-Daten für {aid_info.get('type', 'Unbekannt')}...{Colors.END}")

        # AID selektieren
        try:
            aid_bytes = bytes.fromhex(aid)
            apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)
            data, sw1, sw2 = self.send_apdu(apdu, f"SELECT AID {aid}")

            if sw1 != 0x90 or sw2 != 0x00:
                return emv_data

        except Exception as e:
            logger.error(f"AID-Select-Fehler: {e}")
            return emv_data

        # GPO ausführen
        gpo_response = self.get_processing_options(aid)
        if gpo_response:
            emv_data['gpo_response'] = toHexString(gpo_response)

            # AFL extrahieren (Application File Locator)
            afl_start = None
            for i in range(len(gpo_response) - 1):
                if gpo_response[i] == 0x94:  # AFL Tag
                    afl_length = gpo_response[i + 1]
                    afl_start = i + 2
                    break

            if afl_start:
                afl_data = gpo_response[afl_start:afl_start + afl_length]
                emv_data['afl'] = toHexString(afl_data)

                # Records basierend auf AFL lesen
                for i in range(0, len(afl_data), 4):
                    if i + 3 < len(afl_data):
                        sfi = (afl_data[i] >> 3) & 0x1F
                        first_rec = afl_data[i + 1]
                        last_rec = afl_data[i + 2]

                        for rec_num in range(first_rec, last_rec + 1):
                            record_data = self.read_record(sfi, rec_num)
                            if record_data:
                                self.parse_emv_tags(record_data, emv_data)

        # Direkte Tag-Abfragen
        direct_tags = ['9F36', '9F13', '9F17', '9F4D', '5A', '5F24', '5F20']
        for tag in direct_tags:
            self.get_data_direct(tag, emv_data)

        # Experimentelle SFI-Scans (1-31)
        print(f"{Colors.CYAN}🔬 Experimenteller SFI-Scan...{Colors.END}")
        for sfi in range(1, 32):
            for record in range(1, 6):  # Max 5 Records pro SFI
                record_data = self.read_record(sfi, record)
                if record_data:
                    logger.info(f"  ✅ SFI {sfi} Record {record}: {len(record_data)} Bytes")
                    self.parse_emv_tags(record_data, emv_data)

        return emv_data

    def parse_emv_tags(self, data: List[int], result: Dict[str, Any]) -> None:
        """EMV-Tags aus Daten extrahieren"""
        try:
            data_hex = ''.join([f'{b:02X}' for b in data])

            # Bekannte Tags suchen
            for tag, description in self.emv_tags.items():
                if tag in data_hex:
                    idx = data_hex.index(tag)
                    if idx + len(tag) + 2 < len(data_hex):
                        length = int(data_hex[idx + len(tag):idx + len(tag) + 2], 16)
                        value_start = idx + len(tag) + 2
                        value_end = value_start + (length * 2)

                        if value_end <= len(data_hex):
                            value = data_hex[value_start:value_end]

                            # Spezielle Formatierung
                            if tag == '5A':  # PAN
                                # Maskiere PAN für Sicherheit
                                if len(value) >= 8:
                                    result['pan'] = value[:6] + '*' * (len(value) - 10) + value[-4:]
                                    result['pan_full_hash'] = hash(value)  # Hash für Vergleich
                            elif tag == '5F24':  # Expiry
                                if len(value) == 6:
                                    result['expiry'] = f"{value[2:4]}/{value[0:2]}"
                            elif tag == '5F20':  # Cardholder Name
                                try:
                                    result['cardholder'] = bytes.fromhex(value).decode('ascii').strip()
                                except:
                                    result['cardholder'] = value
                            else:
                                result[f'tag_{tag}'] = value

        except Exception as e:
            logger.error(f"Tag-Parse-Fehler: {e}")

    def get_data_direct(self, tag: str, result: Dict[str, Any]) -> None:
        """Direkter GET DATA Befehl für spezifisches Tag"""
        try:
            tag_bytes = bytes.fromhex(tag)
            apdu = [0x80, 0xCA] + list(tag_bytes) + [0x00]

            data, sw1, sw2 = self.send_apdu(apdu, f"GET DATA {tag}")

            if sw1 == 0x90 and sw2 == 0x00 and data:
                result[f'direct_{tag}'] = toHexString(data)

        except Exception as e:
            logger.error(f"GET DATA Fehler für {tag}: {e}")

    def experimental_methods(self) -> Dict[str, Any]:
        """Experimentelle Methoden für problematische Karten"""
        experimental_data = {}

        print(f"\n{Colors.WARNING}🧪 Starte experimentelle Methoden...{Colors.END}")

        # 1. Alternative SELECT-Varianten
        select_variants = [
            {'p1': 0x04, 'p2': 0x00, 'desc': 'Standard'},
            {'p1': 0x04, 'p2': 0x04, 'desc': 'By Name Next'},
            {'p1': 0x00, 'p2': 0x00, 'desc': 'By ID First'},
            {'p1': 0x02, 'p2': 0x00, 'desc': 'By ID Next'},
        ]

        for variant in select_variants:
            # Test mit Visa AID
            visa_aid = bytes.fromhex('A0000000031010')
            apdu = [0x00, 0xA4, variant['p1'], variant['p2'], len(visa_aid)] + list(visa_aid)

            data, sw1, sw2 = self.send_apdu(apdu, f"SELECT Variante {variant['desc']}")

            if sw1 == 0x90 and sw2 == 0x00:
                experimental_data[f"select_{variant['desc']}"] = toHexString(data)
                print(f"  ✅ {variant['desc']}: Erfolg!")

        # 2. CPLC (Card Production Life Cycle) Daten
        cplc_apdu = [0x80, 0xCA, 0x9F, 0x7F, 0x00]
        data, sw1, sw2 = self.send_apdu(cplc_apdu, "GET CPLC DATA")
        if sw1 == 0x90 and sw2 == 0x00:
            experimental_data['cplc'] = toHexString(data)

        # 3. PayPal/Wallet-spezifische Methoden
        # PayPal verwendet oft proprietäre AIDs
        paypal_aids = [
            '325041592E5359532E4444463031',  # PayPal bekannt
            'A0000006510100',  # Alternative PayPal
            'A0000000651010',  # JCB/PayPal gemeinsam
        ]

        for aid in paypal_aids:
            try:
                aid_bytes = bytes.fromhex(aid)
                apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)

                data, sw1, sw2 = self.send_apdu(apdu, f"PayPal Test {aid[:8]}...")

                if sw1 == 0x90 and sw2 == 0x00:
                    experimental_data[f'paypal_{aid[:8]}'] = toHexString(data)
                    print(f"  ✅ PayPal AID gefunden: {aid}")

            except Exception as e:
                logger.error(f"PayPal-Test-Fehler: {e}")

        # 4. Visa-spezifische Optimierungen
        # Visa Debit/Credit unterschiedliche AIDs
        visa_specific = {
            'Visa Credit': 'A0000000031010',
            'Visa Debit': 'A0000000032010',
            'Visa Plus': 'A0000000038010',
            'V PAY': 'A0000000032020',
            'Visa Interlink': 'A0000000039010'
        }

        for name, aid in visa_specific.items():
            try:
                aid_bytes = bytes.fromhex(aid)
                apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes) + [0x00]

                data, sw1, sw2 = self.send_apdu(apdu, f"Visa {name}")

                if sw1 == 0x90 and sw2 == 0x00:
                    experimental_data[f'visa_{name.lower().replace(" ", "_")}'] = {
                        'found': True,
                        'fci': toHexString(data)
                    }
                    print(f"  ✅ {name} erkannt!")

                    # Versuche GPO mit verschiedenen PDOLs
                    gpo_variants = [
                        [0x80, 0xA8, 0x00, 0x00, 0x02, 0x83, 0x00],
                        [0x80, 0xA8, 0x00, 0x00, 0x00],
                        [0x80, 0xA8, 0x00, 0x00, 0x23, 0x83, 0x21,
                         0x00, 0x00, 0x00, 0x00, 0x00, 0x01,  # Amount
                         0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Other Amount
                         0x09, 0x78,  # Country Code
                         0x00, 0x00, 0x00, 0x00, 0x00,  # TVR
                         0x09, 0x78,  # Currency Code
                         0x24, 0x01, 0x25,  # Date
                         0x00,  # Transaction Type
                         0x12, 0x34, 0x56, 0x78]  # Unpredictable Number
                    ]

                    for idx, gpo in enumerate(gpo_variants):
                        gpo_data, gpo_sw1, gpo_sw2 = self.send_apdu(gpo, f"GPO Variante {idx + 1}")
                        if gpo_sw1 == 0x90 and gpo_sw2 == 0x00:
                            experimental_data[f'visa_{name.lower()}_gpo'] = toHexString(gpo_data)
                            break

            except Exception as e:
                logger.error(f"Visa-Test-Fehler für {name}: {e}")

        self.current_test['experimental_findings'] = experimental_data
        return experimental_data

    def test_card_comprehensive(self, card_name: str = "") -> Dict[str, Any]:
        """Umfassender Kartentest mit allen Methoden"""
        print(f"\n{Colors.HEADER}{'=' * 50}")
        print(f"🔍 UMFASSENDE KARTENANALYSE")
        print(f"{'=' * 50}{Colors.END}\n")

        # Kartenname abfragen
        if not card_name:
            card_name = input(f"{Colors.CYAN}Kartenname (z.B. 'Visa Credit', 'PayPal'): {Colors.END}")

        self.current_test = {
            'card_name': card_name,
            'timestamp': datetime.now().isoformat(),
            'errors': []
        }

        # Verbindung herstellen
        if not self.connect_to_reader():
            self.current_test['errors'].append("Keine Verbindung zum Reader/Karte")
            return self.current_test

        try:
            # 1. ATR auslesen
            print(f"\n{Colors.BOLD}1. BASIS-INFORMATIONEN{Colors.END}")
            self.get_atr()

            # 2. PSE/PPSE versuchen
            print(f"\n{Colors.BOLD}2. PAYMENT SYSTEM ENVIRONMENT{Colors.END}")
            pse_found = self.select_pse()

            # 3. AID-Discovery
            print(f"\n{Colors.BOLD}3. APPLICATION DISCOVERY{Colors.END}")
            found_aids = self.brute_force_aids()

            if not found_aids:
                print(f"{Colors.WARNING}⚠️ Keine Standard-AIDs gefunden - starte erweiterte Suche...{Colors.END}")

            # 4. EMV-Daten für jede gefundene AID
            print(f"\n{Colors.BOLD}4. EMV-DATENEXTRAKTION{Colors.END}")
            all_emv_data = {}
            for aid_info in found_aids:
                emv_data = self.extract_emv_data(aid_info)
                if emv_data:
                    all_emv_data[aid_info['aid']] = emv_data

            self.current_test['emv_data'] = all_emv_data

            # 5. Experimentelle Methoden
            print(f"\n{Colors.BOLD}5. EXPERIMENTELLE METHODEN{Colors.END}")
            self.experimental_methods()

            # 6. Zusammenfassung
            print(f"\n{Colors.HEADER}{'=' * 50}")
            print(f"📊 ANALYSE-ZUSAMMENFASSUNG")
            print(f"{'=' * 50}{Colors.END}\n")

            print(f"✅ Karte: {card_name}")
            print(f"✅ AIDs gefunden: {len(found_aids)}")
            if found_aids:
                for aid in found_aids:
                    print(f"  • {aid['type']}: {aid['aid']}")

            if 'pan' in self.current_test.get('emv_data', {}).get(found_aids[0]['aid'] if found_aids else '', {}):
                print(f"✅ PAN erkannt: {self.current_test['emv_data'][found_aids[0]['aid']]['pan']}")

            if 'expiry' in self.current_test.get('emv_data', {}).get(found_aids[0]['aid'] if found_aids else '', {}):
                print(f"✅ Ablaufdatum: {self.current_test['emv_data'][found_aids[0]['aid']]['expiry']}")

            print(f"✅ APDU-Befehle gesendet: {len(self.current_test.get('raw_apdus', []))}")
            print(f"✅ Experimentelle Funde: {len(self.current_test.get('experimental_findings', {}))}")

        except Exception as e:
            logger.error(f"Testfehler: {e}")
            self.current_test['errors'].append(str(e))
            traceback.print_exc()

        finally:
            if self.connection:
                self.connection.disconnect()

        return self.current_test

    def save_results(self, filename: str = None) -> str:
        """Testergebnisse in JSON speichern"""
        if not filename:
            filename = f"kartentest_results_{self.session_id}.json"

        filepath = os.path.join("data", filename)
        os.makedirs("data", exist_ok=True)

        # Existierende Daten laden
        existing_data = {'test_sessions': []}
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    existing_data = json.load(f)
            except:
                pass

        # Neue Session hinzufügen
        existing_data['test_sessions'].append({
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'card_tests': self.test_results
        })

        # Speichern
        with open(filepath, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"\n{Colors.GREEN}✅ Ergebnisse gespeichert in: {filepath}{Colors.END}")
        return filepath

    def generate_report(self) -> str:
        """Human-readable Report generieren"""
        report = []
        report.append("=" * 60)
        report.append("NFC KARTENANALYSE REPORT")
        report.append(f"Session: {self.session_id}")
        report.append(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)

        for test in self.test_results:
            report.append(f"\nKarte: {test.get('card_name', 'Unbekannt')}")
            report.append("-" * 40)

            # ATR
            if 'atr' in test:
                report.append(f"ATR: {test['atr']}")

            # AIDs
            aids = test.get('aids_found', [])
            if aids:
                report.append(f"\nGefundene Applications ({len(aids)}):")
                for aid in aids:
                    report.append(f"  • {aid['type']}: {aid['aid']}")
            else:
                report.append("\n⚠️ KEINE Standard-AIDs gefunden!")

            # EMV-Daten
            emv = test.get('emv_data', {})
            if emv:
                report.append("\nEMV-Daten:")
                for aid, data in emv.items():
                    if 'pan' in data:
                        report.append(f"  PAN: {data['pan']}")
                    if 'expiry' in data:
                        report.append(f"  Ablauf: {data['expiry']}")
                    if 'cardholder' in data:
                        report.append(f"  Inhaber: {data['cardholder']}")

            # Experimentelle Funde
            exp = test.get('experimental_findings', {})
            if exp:
                report.append(f"\nExperimentelle Funde: {len(exp)} Einträge")
                for key in list(exp.keys())[:5]:  # Erste 5 anzeigen
                    report.append(f"  • {key}")

            # Fehler
            errors = test.get('errors', [])
            if errors:
                report.append(f"\n⚠️ Fehler: {', '.join(errors)}")

            # Statistik
            apdus = test.get('raw_apdus', [])
            if apdus:
                total_time = sum(a.get('time_ms', 0) for a in apdus)
                report.append(f"\nStatistik:")
                report.append(f"  APDUs gesendet: {len(apdus)}")
                report.append(f"  Gesamtzeit: {total_time}ms")
                report.append(f"  Ø Zeit/APDU: {total_time // len(apdus) if apdus else 0}ms")

        report_text = '\n'.join(report)

        # Report speichern
        report_file = f"kartentest_report_{self.session_id}.txt"
        with open(report_file, 'w') as f:
            f.write(report_text)

        print(f"\n{Colors.GREEN}✅ Report gespeichert in: {report_file}{Colors.END}")
        return report_text

    def compare_cards(self, card1_idx: int = 0, card2_idx: int = 1) -> None:
        """Zwei Kartentests vergleichen"""
        if len(self.test_results) < 2:
            print(f"{Colors.WARNING}⚠️ Mindestens 2 Kartentests erforderlich{Colors.END}")
            return

        c1 = self.test_results[card1_idx]
        c2 = self.test_results[card2_idx]

        print(f"\n{Colors.HEADER}KARTENVERGLEICH{Colors.END}")
        print(f"Karte 1: {c1.get('card_name', 'Unbekannt')}")
        print(f"Karte 2: {c2.get('card_name', 'Unbekannt')}")
        print("-" * 40)

        # ATR-Vergleich
        if c1.get('atr') != c2.get('atr'):
            print(f"ATR unterschiedlich:")
            print(f"  1: {c1.get('atr', 'N/A')}")
            print(f"  2: {c2.get('atr', 'N/A')}")
        else:
            print(f"ATR identisch: {c1.get('atr', 'N/A')}")

        # AID-Vergleich
        aids1 = {a['aid'] for a in c1.get('aids_found', [])}
        aids2 = {a['aid'] for a in c2.get('aids_found', [])}

        only_in_1 = aids1 - aids2
        only_in_2 = aids2 - aids1
        common = aids1 & aids2

        if only_in_1:
            print(f"\nNur in Karte 1:")
            for aid in only_in_1:
                print(f"  • {aid}")

        if only_in_2:
            print(f"\nNur in Karte 2:")
            for aid in only_in_2:
                print(f"  • {aid}")

        if common:
            print(f"\nGemeinsame AIDs:")
            for aid in common:
                print(f"  • {aid}")


def interactive_menu():
    """Interaktives CLI-Menü"""
    tester = CardTester()

    while True:
        print(f"\n{Colors.HEADER}╔═══════════════════════════════════════╗")
        print(f"║     NFC-KARTENANALYSE-TOOL v2.0      ║")
        print(f"║         Raspberry Pi 4b / ACR122U     ║")
        print(f"╚═══════════════════════════════════════╝{Colors.END}")

        print(f"\n{Colors.CYAN}Optionen:{Colors.END}")
        print("1. 🔍 Einzelne Karte testen")
        print("2. 🔁 Mehrere Karten testen")
        print("3. 📊 Vergleich durchführen")
        print("4. 💾 Ergebnisse speichern")
        print("5. 📄 Report generieren")
        print("6. 🚀 Schnelltest (Visa/PayPal-Fokus)")
        print("7. ❌ Beenden")

        choice = input(f"\n{Colors.BOLD}Wahl (1-7): {Colors.END}")

        if choice == '1':
            result = tester.test_card_comprehensive()
            tester.test_results.append(result)
            print(f"\n{Colors.GREEN}✅ Test abgeschlossen!{Colors.END}")

        elif choice == '2':
            num = int(input("Anzahl Karten: "))
            for i in range(num):
                print(f"\n{Colors.BOLD}Karte {i + 1} von {num}{Colors.END}")
                result = tester.test_card_comprehensive()
                tester.test_results.append(result)
                if i < num - 1:
                    input(f"\n{Colors.CYAN}Enter für nächste Karte...{Colors.END}")

        elif choice == '3':
            if len(tester.test_results) >= 2:
                tester.compare_cards()
            else:
                print(f"{Colors.WARNING}⚠️ Erst mindestens 2 Karten testen!{Colors.END}")

        elif choice == '4':
            tester.save_results()

        elif choice == '5':
            tester.generate_report()

        elif choice == '6':
            # Schnelltest mit Fokus auf Visa/PayPal
            print(f"\n{Colors.CYAN}Schnelltest für Visa/PayPal-Karten{Colors.END}")
            result = tester.test_card_comprehensive("Schnelltest Visa/PayPal")
            tester.test_results.append(result)

            # Automatisch speichern
            tester.save_results("schnelltest_visa_paypal.json")
            tester.generate_report()

        elif choice == '7':
            print(f"\n{Colors.GREEN}Auf Wiedersehen!{Colors.END}")
            break

        else:
            print(f"{Colors.WARNING}⚠️ Ungültige Eingabe{Colors.END}")


def main():
    """Hauptprogramm mit Argumenten"""
    parser = argparse.ArgumentParser(description='NFC Kartenanalyse-Tool')
    parser.add_argument('--quick', action='store_true', help='Schnelltest durchführen')
    parser.add_argument('--card', type=str, help='Kartenname für Test')
    parser.add_argument('--output', type=str, help='Ausgabedatei für Ergebnisse')

    args = parser.parse_args()

    if args.quick:
        # Schnelltest-Modus
        tester = CardTester()
        card_name = args.card or "Schnelltest"
        result = tester.test_card_comprehensive(card_name)
        tester.test_results.append(result)

        output_file = args.output or f"schnelltest_{tester.session_id}.json"
        tester.save_results(output_file)
        tester.generate_report()
    else:
        # Interaktiver Modus
        interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Programm durch Benutzer beendet{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Kritischer Fehler: {e}{Colors.END}")
        traceback.print_exc()