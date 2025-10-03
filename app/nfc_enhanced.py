"""
Enhanced NFC Reader Module - Verbesserte Kartenerkennung
=========================================================
Optimierungen für bessere deutsche Karten-Unterstützung und Timeout-Management
"""

import logging
import threading
import queue
import time
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================
# KONFIGURATION
# ============================================

@dataclass
class NFCTimeoutConfig:
    """Konfigurierbare Timeout-Werte für robuste NFC-Operationen."""
    APDU_TIMEOUT: float = 3.0          # 3 Sekunden für APDU-Kommandos
    CONNECTION_TIMEOUT: float = 5.0     # 5 Sekunden für Kartenverbindung
    RETRY_ATTEMPTS: int = 3             # 3 Wiederholungsversuche
    RETRY_DELAY: float = 0.5            # 500ms zwischen Versuchen
    CARD_DETECTION_TIMEOUT: float = 2.0 # 2 Sekunden für Kartenerkennung

# ============================================
# ERWEITERTE DEUTSCHE KARTEN-UNTERSTÜTZUNG
# ============================================

ENHANCED_GERMAN_AIDS = [
    # Neue Girocard-Standards
    ("D27600004455454E4C4158", "Girocard Classic"),
    ("D27600002545500401", "Deutsche Bank EC"),
    ("D276000025455005", "Commerzbank Girocard"),
    ("D276000025455006", "Postbank Girocard"),
    ("D276000025455007", "DKB Girocard"),
    
    # Regionale Sparkassen-AIDs
    ("D276000024010205", "Sparkasse Erweitert"),
    ("D276000024010206", "Sparkasse Premium+"),
    ("D276000024010207", "Sparkasse Business"),
    
    # Genossenschaftsbanken
    ("D276000012401001", "Volksbank Standard"),
    ("D276000012401002", "Raiffeisenbank"),
    ("D276000012401003", "Sparda Bank"),
    
    # Bestehende deutsche AIDs (aus Original)
    ("D27600002545413100", "Girocard Standard"),
    ("D2760000254541", "Girocard Alt"),
    ("D276000025", "Girocard Basic"),
    ("D27600002547410100", "VR-BankCard"),
    ("D27600002401010", "Deutsche Kreditbank"),
    ("D276000024010101", "Sparkasse EC"),
    ("D276000024010102", "Sparkasse Girocard"),
    ("D276000024010103", "Sparkasse Plus"),
    ("D276000024010104", "Sparkasse Gold"),
]

# PSE (Payment System Environment) für deutsche Karten
GERMAN_PSE_AIDS = [
    "325041592E5359532E4444463031",  # German PSE
    "315041592E5359532E4444463031",  # Alternative German PSE
    "1PAY.SYS.DDF01",                 # Standard PSE
    "2PAY.SYS.DDF01"                  # Alternative PSE
]

# ============================================
# TIMEOUT-MANAGEMENT
# ============================================

def transmit_with_timeout(connection, apdu: List[int], 
                         timeout: float = NFCTimeoutConfig.APDU_TIMEOUT) -> Tuple[Optional[List], int, int, Optional[str]]:
    """
    Thread-basierte APDU-Übertragung mit konfigurierbarem Timeout.
    
    Returns:
        Tuple von (response, sw1, sw2, error_msg)
    """
    result_queue = queue.Queue()
    
    def transmit_worker():
        try:
            response, sw1, sw2 = connection.transmit(apdu)
            result_queue.put(('success', response, sw1, sw2))
        except Exception as e:
            result_queue.put(('error', str(e)))
    
    thread = threading.Thread(target=transmit_worker, daemon=True)
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        logger.warning(f"APDU Timeout nach {timeout}s für Command: {' '.join(f'{b:02X}' for b in apdu[:4])}")
        return None, 0x00, 0x00, "TIMEOUT"
    
    try:
        result = result_queue.get_nowait()
        if result[0] == 'success':
            return result[1], result[2], result[3], None
        else:
            return None, 0x00, 0x00, result[1]
    except queue.Empty:
        return None, 0x00, 0x00, "NO_RESPONSE"

def retry_with_backoff(func, *args, max_attempts: int = NFCTimeoutConfig.RETRY_ATTEMPTS, 
                       delay: float = NFCTimeoutConfig.RETRY_DELAY, **kwargs):
    """
    Führt eine Funktion mit Retry-Logic und exponentiallem Backoff aus.
    """
    for attempt in range(max_attempts):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            logger.debug(f"Versuch {attempt + 1}/{max_attempts} fehlgeschlagen: {e}")
        
        if attempt < max_attempts - 1:
            wait_time = delay * (2 ** attempt)  # Exponentieller Backoff
            time.sleep(wait_time)
    
    return None

# ============================================
# GIROCARD-DETECTION-PIPELINE
# ============================================

def enhanced_girocard_detection(connection) -> Optional[Tuple[str, str]]:
    """
    Spezialisierte Girocard-Erkennung für deutsche EC-Karten.
    
    Returns:
        Tuple von (pan, expiry_date) oder None
    """
    logger.info("🔍 Starte erweiterte Girocard-Erkennung...")
    
    # Phase 1: PSE-basierte Erkennung
    for pse_aid in GERMAN_PSE_AIDS:
        try:
            if isinstance(pse_aid, str) and not pse_aid.startswith("1PAY") and not pse_aid.startswith("2PAY"):
                pse_bytes = bytes.fromhex(pse_aid)
            else:
                pse_bytes = pse_aid.encode() if isinstance(pse_aid, str) else pse_aid
            
            select_pse = [0x00, 0xA4, 0x04, 0x00, len(pse_bytes)] + list(pse_bytes)
            response, sw1, sw2, error = transmit_with_timeout(connection, select_pse, timeout=2.0)
            
            if sw1 == 0x90 and sw2 == 0x00:
                logger.info(f"✅ PSE erfolgreich ausgewählt: {pse_aid}")
                # Versuche SFI-basiertes Lesen
                pan, expiry = read_girocard_sfi_records(connection)
                if pan:
                    return pan, expiry
        except Exception as e:
            logger.debug(f"PSE {pse_aid} fehlgeschlagen: {e}")
    
    # Phase 2: Low-Level ISO 7816-4 Commands für Offline-Karten
    iso_commands = [
        ([0x00, 0xCA, 0x00, 0x9F], "GET DATA - Card Info"),
        ([0x00, 0xCA, 0xDF, 0x20], "GET DATA - Sparkasse"),
        ([0x00, 0xCA, 0xDF, 0x30], "GET DATA - Volksbank"),
        ([0x00, 0xB0, 0x00, 0x00, 0x00], "READ BINARY"),
        ([0x00, 0xB2, 0x01, 0x0C, 0x00], "READ RECORD - SFI 01"),
        ([0x00, 0xB2, 0x01, 0x14, 0x00], "READ RECORD - SFI 02"),
    ]
    
    for cmd, description in iso_commands:
        try:
            response, sw1, sw2, error = transmit_with_timeout(connection, cmd, timeout=2.0)
            
            if response and len(response) > 10:
                logger.debug(f"ISO Command '{description}' erfolgreich: {len(response)} bytes")
                # Versuche PAN aus Antwort zu extrahieren
                pan = extract_pan_from_raw(response)
                if pan:
                    return pan, None
        except Exception as e:
            logger.debug(f"ISO Command '{description}' fehlgeschlagen: {e}")
    
    # Phase 3: Bank-spezifische Kommandos
    bank_specific_commands = {
        'sparkasse': [
            [0x80, 0xCA, 0xDF, 0x20, 0x00],  # Sparkasse-spezifisch
            [0x80, 0xCA, 0xDF, 0x21, 0x00],  # Sparkasse erweitert
            [0x00, 0xCA, 0x01, 0xA4, 0x00],  # Sparkasse Kartennummer
        ],
        'volksbank': [
            [0x80, 0xCA, 0xDF, 0x30, 0x00],  # VR-Bank-spezifisch
            [0x00, 0xCA, 0x01, 0xB0, 0x00],  # VR-Bank Kartennummer
        ],
        'deutsche_bank': [
            [0x80, 0xCA, 0xDF, 0x40, 0x00],  # Deutsche Bank
            [0x00, 0xCA, 0x01, 0xC0, 0x00],  # Deutsche Bank Kartennummer
        ]
    }
    
    for bank, commands in bank_specific_commands.items():
        for cmd in commands:
            try:
                response, sw1, sw2, error = transmit_with_timeout(connection, cmd, timeout=2.0)
                
                if response and len(response) > 8:
                    logger.info(f"✅ {bank.title()}-spezifisches Kommando erfolgreich")
                    pan = extract_pan_from_raw(response)
                    if pan:
                        return pan, None
            except Exception as e:
                logger.debug(f"{bank.title()} Command fehlgeschlagen: {e}")
    
    return None

def read_girocard_sfi_records(connection) -> Tuple[Optional[str], Optional[str]]:
    """
    Liest Girocard-Daten über SFI (Short File Identifier) Records.
    """
    # Standard SFIs für deutsche Karten
    sfi_ranges = [
        (0x01, 0x10),  # Standard-Bereich
        (0x11, 0x20),  # Erweitert
    ]
    
    for sfi_start, sfi_end in sfi_ranges:
        for sfi in range(sfi_start, sfi_end):
            for record in range(1, 5):  # Meist nur 1-4 Records
                cmd = [0x00, 0xB2, record, (sfi << 3) | 0x04, 0x00]
                
                response, sw1, sw2, error = transmit_with_timeout(connection, cmd, timeout=1.0)
                
                if response and len(response) > 10:
                    # Parse EMV-TLV-Daten
                    pan = extract_pan_from_tlv(response)
                    expiry = extract_expiry_from_tlv(response)
                    
                    if pan:
                        logger.info(f"✅ Girocard-Daten gefunden in SFI {sfi:02X}, Record {record}")
                        return pan, expiry
    
    return None, None

def extract_pan_from_raw(data: List[int]) -> Optional[str]:
    """
    Extrahiert PAN aus Rohdaten mit verschiedenen Heuristiken.
    """
    if not data or len(data) < 8:
        return None
    
    # Methode 1: Suche nach BCD-kodierten Ziffernfolgen
    for i in range(len(data) - 7):
        # Prüfe ob es wie eine Kartennummer aussieht (BCD)
        if all(0x00 <= b <= 0x99 for b in data[i:i+8]):
            potential_pan = ""
            for byte in data[i:i+10]:  # Bis zu 20 Ziffern
                if byte == 0xFF or byte == 0x00:
                    break
                high = (byte >> 4) & 0x0F
                low = byte & 0x0F
                if high <= 9:
                    potential_pan += str(high)
                if low <= 9 and low != 0x0F:
                    potential_pan += str(low)
            
            # Validiere Länge
            if 12 <= len(potential_pan) <= 19:
                if validate_luhn(potential_pan):
                    logger.debug(f"PAN aus Rohdaten extrahiert: {potential_pan[:4]}****")
                    return potential_pan
    
    # Methode 2: ASCII-kodierte Kartennummer
    try:
        ascii_data = bytes(data).decode('ascii', errors='ignore')
        import re
        matches = re.findall(r'\d{12,19}', ascii_data)
        for match in matches:
            if validate_luhn(match):
                logger.debug(f"ASCII-PAN gefunden: {match[:4]}****")
                return match
    except:
        pass
    
    return None

def extract_pan_from_tlv(data: List[int]) -> Optional[str]:
    """
    Extrahiert PAN aus TLV-strukturierten Daten.
    """
    # EMV-Tags für PAN
    pan_tags = [0x5A, 0x57, 0x9F6B]
    
    i = 0
    while i < len(data) - 2:
        tag = data[i]
        
        # Multi-byte tag handling
        if tag == 0x9F:
            if i + 1 < len(data):
                tag = (tag << 8) | data[i + 1]
                i += 1
        
        i += 1
        if i >= len(data):
            break
        
        length = data[i]
        i += 1
        
        if i + length > len(data):
            break
        
        value = data[i:i + length]
        
        # Prüfe auf PAN-Tags
        if tag in pan_tags:
            pan = bcd_to_str(value)
            if pan and validate_luhn(pan):
                return pan
        
        i += length
    
    return None

def extract_expiry_from_tlv(data: List[int]) -> Optional[str]:
    """
    Extrahiert Ablaufdatum aus TLV-strukturierten Daten.
    """
    # EMV-Tag für Ablaufdatum
    expiry_tag = 0x5F24
    
    i = 0
    while i < len(data) - 4:
        if data[i] == 0x5F and data[i + 1] == 0x24:
            length = data[i + 2]
            if length == 3 and i + 5 < len(data):
                # Format: YYMMDD (BCD)
                value = data[i + 3:i + 6]
                yy = f"{(value[0] >> 4) & 0x0F}{value[0] & 0x0F}"
                mm = f"{(value[1] >> 4) & 0x0F}{value[1] & 0x0F}"
                return f"{mm}/{yy}"
        i += 1
    
    return None

# ============================================
# ERROR-PATTERN-ANALYSE
# ============================================

class CardFailureAnalyzer:
    """Intelligente Analyse von Kartenfehlern für bessere Erkennung."""
    
    def __init__(self):
        self.error_patterns = {
            'sparkasse_security': {
                'errors': ['6A82', '6985', '6A81'],
                'threshold': 0.8,
                'recommendation': 'Sparkassen-Sicherheit blockiert - Versuche Offline-Modus oder Girocard-Pipeline'
            },
            'girocard_offline': {
                'errors': ['6D00', '6E00'],
                'threshold': 0.6,
                'recommendation': 'Offline-Girocard erkannt - Verwende ISO 7816 Basic Commands'
            },
            'damaged_card': {
                'errors': ['6F00', '6C00', '6700'],
                'threshold': 0.5,
                'recommendation': 'Möglicher Kartenschaden - Bitte Karte reinigen oder erneut auflegen'
            },
            'wrong_protocol': {
                'errors': ['6A86', '6A87'],
                'threshold': 0.7,
                'recommendation': 'Falsches Protokoll - Wechsle zwischen T=0 und T=1'
            },
            'authentication_required': {
                'errors': ['6300', '6983', '6984'],
                'threshold': 0.6,
                'recommendation': 'PIN/Authentifizierung erforderlich - Karte ist gesperrt'
            }
        }
        
        self.error_history = []
        
    def analyze_errors(self, sw1: int, sw2: int) -> Dict[str, Any]:
        """Analysiert einen Fehlercode und gibt Empfehlungen."""
        error_code = f"{sw1:02X}{sw2:02X}"
        self.error_history.append(error_code)
        
        # Behalte nur die letzten 20 Fehler
        if len(self.error_history) > 20:
            self.error_history = self.error_history[-20:]
        
        # Analysiere Muster
        for pattern_name, pattern_data in self.error_patterns.items():
            matching_errors = [e for e in self.error_history if e in pattern_data['errors']]
            
            if len(matching_errors) / max(len(self.error_history), 1) >= pattern_data['threshold']:
                return {
                    'pattern': pattern_name,
                    'confidence': len(matching_errors) / len(self.error_history),
                    'recommendation': pattern_data['recommendation'],
                    'action': self.get_fallback_action(pattern_name)
                }
        
        return {
            'pattern': 'unknown',
            'confidence': 0.0,
            'recommendation': 'Unbekanntes Fehlermuster - Standard-Fallback verwenden',
            'action': 'standard_fallback'
        }
    
    def get_fallback_action(self, pattern: str) -> str:
        """Gibt eine konkrete Fallback-Aktion basierend auf dem Muster zurück."""
        actions = {
            'sparkasse_security': 'use_girocard_pipeline',
            'girocard_offline': 'use_iso_commands',
            'damaged_card': 'retry_with_cleaning',
            'wrong_protocol': 'switch_protocol',
            'authentication_required': 'skip_card'
        }
        return actions.get(pattern, 'standard_fallback')

# ============================================
# PERFORMANCE-CACHING
# ============================================

class NFCPerformanceCache:
    """Cache für optimierte NFC-Operationen."""
    
    def __init__(self, max_size: int = 100):
        self.aid_cache: Dict[str, List[str]] = {}  # Erfolgreiche AIDs pro Kartenhash
        self.card_type_cache: Dict[str, str] = {}   # Kartentyp pro Kartenhash
        self.timing_cache: Dict[str, float] = {}    # Durchschnittliche Antwortzeit
        self.max_size = max_size
        
    def get_optimized_aid_sequence(self, card_hash: str, default_aids: List[str]) -> List[str]:
        """
        Holt optimierte AID-Sequenz basierend auf vorherigen Erfolgen.
        Priorisiert erfolgreiche AIDs und sortiert nach Geschwindigkeit.
        """
        if card_hash in self.aid_cache:
            successful_aids = self.aid_cache[card_hash]
            
            # Sortiere nach Geschwindigkeit
            sorted_aids = sorted(successful_aids, 
                               key=lambda aid: self.timing_cache.get(f"{card_hash}_{aid}", 999))
            
            # Kombiniere mit Default-AIDs (erfolgreiche zuerst)
            remaining_aids = [aid for aid in default_aids if aid not in sorted_aids]
            return sorted_aids + remaining_aids
        
        return default_aids
    
    def cache_successful_operation(self, card_hash: str, aid: str, 
                                  card_type: str, response_time: float):
        """Cacht eine erfolgreiche Operation für zukünftige Optimierung."""
        # AID-Cache
        if card_hash not in self.aid_cache:
            self.aid_cache[card_hash] = []
        
        if aid not in self.aid_cache[card_hash]:
            self.aid_cache[card_hash].insert(0, aid)  # Neueste zuerst
            
            # Begrenze Cache-Größe
            if len(self.aid_cache[card_hash]) > 10:
                self.aid_cache[card_hash] = self.aid_cache[card_hash][:10]
        
        # Kartentyp-Cache
        self.card_type_cache[card_hash] = card_type
        
        # Timing-Cache (gleitender Durchschnitt)
        cache_key = f"{card_hash}_{aid}"
        if cache_key in self.timing_cache:
            # Gleitender Durchschnitt
            self.timing_cache[cache_key] = (self.timing_cache[cache_key] + response_time) / 2
        else:
            self.timing_cache[cache_key] = response_time
        
        # Cleanup wenn Cache zu groß
        if len(self.aid_cache) > self.max_size:
            # Entferne älteste Einträge
            oldest = list(self.aid_cache.keys())[0]
            del self.aid_cache[oldest]
            if oldest in self.card_type_cache:
                del self.card_type_cache[oldest]
    
    def get_cached_card_type(self, card_hash: str) -> Optional[str]:
        """Holt gecachten Kartentyp falls vorhanden."""
        return self.card_type_cache.get(card_hash)

# ============================================
# HILFSFUNKTIONEN
# ============================================

def bcd_to_str(bcd_bytes: List[int]) -> str:
    """Konvertiert BCD-kodierte Bytes zu String."""
    result = ""
    for byte in bcd_bytes:
        if byte == 0xFF:
            break
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        if high <= 9:
            result += str(high)
        if low <= 9 and low != 0x0F:
            result += str(low)
    return result

def validate_luhn(pan: str) -> bool:
    """Validiert eine PAN mit dem Luhn-Algorithmus."""
    if not pan or not pan.isdigit():
        return False
    
    digits = [int(d) for d in pan]
    checksum = 0
    
    # Von rechts nach links, jede zweite Ziffer verdoppeln
    for i in range(len(digits) - 2, -1, -2):
        doubled = digits[i] * 2
        if doubled > 9:
            doubled = doubled - 9
        digits[i] = doubled
    
    return sum(digits) % 10 == 0

# ============================================
# EXPORT
# ============================================

__all__ = [
    'NFCTimeoutConfig',
    'ENHANCED_GERMAN_AIDS',
    'transmit_with_timeout',
    'retry_with_backoff',
    'enhanced_girocard_detection',
    'CardFailureAnalyzer',
    'NFCPerformanceCache',
    'validate_luhn'
]

# === ADDED MISSING VALIDATION FUNCTIONS ===

def enhanced_luhn_validation(pan_str):
    """
    Enhanced Luhn algorithm validation with better error handling.
    Implements ISO/IEC 7812-1 standard.
    """
    try:
        if not pan_str or not isinstance(pan_str, str):
            return False

        # Remove spaces and hyphens
        pan_clean = ''.join(c for c in pan_str if c.isdigit())

        # PAN length validation (8-19 digits per ISO/IEC 7812-1)
        if len(pan_clean) < 8 or len(pan_clean) > 19:
            return False

        # Luhn algorithm (Modulus 10)
        def luhn_checksum(pan):
            total = 0
            reverse_digits = pan[::-1]

            for i, digit in enumerate(reverse_digits):
                n = int(digit)
                if i % 2 == 1:  # Every second digit from right
                    n *= 2
                    if n > 9:
                        n = (n // 10) + (n % 10)
                total += n

            return total % 10 == 0

        return luhn_checksum(pan_clean)

    except Exception:
        return False

def advanced_expiry_validation(expiry_str):
    """
    Advanced expiry date validation with multiple format support.
    Handles YYMM, MMYY, and various other formats.
    """
    from datetime import datetime

    try:
        if not expiry_str or len(expiry_str) < 4:
            return None

        expiry_clean = ''.join(c for c in expiry_str if c.isdigit())
        if len(expiry_clean) < 4:
            return None

        # Try YYMM format (most common)
        yy = expiry_clean[:2]
        mm = expiry_clean[2:4]

        try:
            year = int(yy)
            month = int(mm)

            # Check if month is valid
            if 1 <= month <= 12:
                # Determine century
                current_year = datetime.now().year % 100
                if year < 50:  # Assume 20xx for years < 50
                    full_year = 2000 + year
                else:  # Assume 19xx for years >= 50
                    full_year = 1900 + year

                # Additional validation: card should not be expired too far in past
                if full_year < 2015:
                    # Try MMYY format instead
                    mm = expiry_clean[:2]
                    yy = expiry_clean[2:4]
                    month = int(mm)
                    year = int(yy)
                    if 1 <= month <= 12:
                        if year < 50:
                            full_year = 2000 + year
                        else:
                            full_year = 1900 + year
                        if full_year >= 2015:
                            return f"{month:02d}/{full_year}"
                    return None

                return f"{month:02d}/{full_year}"

            # If month invalid in YYMM, try MMYY
            mm = expiry_clean[:2]
            yy = expiry_clean[2:4]
            month = int(mm)
            year = int(yy)

            if 1 <= month <= 12:
                if year < 50:
                    full_year = 2000 + year
                else:
                    full_year = 1900 + year

                if full_year >= 2015:  # Sanity check
                    return f"{month:02d}/{full_year}"

        except ValueError:
            pass

        return None

    except Exception:
        return None

def robust_bcd_decode(hex_str, strict_mode=False):
    """
    Robust BCD decoding with multiple fallback methods.
    Supports both standard BCD and packed BCD.
    """
    try:
        if not hex_str or len(hex_str) % 2 != 0:
            return ""

        methods = []

        # Method 1: Standard BCD (4-bit nibbles)
        standard_bcd = ""
        for i in range(0, len(hex_str), 2):
            if i + 2 <= len(hex_str):
                byte_val = int(hex_str[i:i+2], 16)
                upper_nibble = (byte_val >> 4) & 0x0F
                lower_nibble = byte_val & 0x0F

                # BCD validity check (0-9)
                if upper_nibble <= 9:
                    standard_bcd += str(upper_nibble)
                elif not strict_mode and upper_nibble == 0xF:
                    pass  # F is padding, ignore
                elif strict_mode:
                    break  # Invalid BCD

                if lower_nibble <= 9:
                    standard_bcd += str(lower_nibble)
                elif not strict_mode and lower_nibble == 0xF:
                    pass  # F is padding, ignore
                elif strict_mode:
                    break  # Invalid BCD

        methods.append(("Standard BCD", standard_bcd))

        # Method 2: Packed BCD (byte-oriented)
        packed_bcd = ""
        for i in range(0, len(hex_str), 2):
            if i + 2 <= len(hex_str):
                byte_str = hex_str[i:i+2]
                # Check for valid decimal
                if byte_str.isdigit() or (int(byte_str, 16) <= 99):
                    decimal_val = int(byte_str, 16)
                    if decimal_val <= 99:
                        packed_bcd += f"{decimal_val:02d}"

        methods.append(("Packed BCD", packed_bcd))

        # Method 3: Little-Endian BCD
        little_endian_bcd = ""
        for i in range(0, len(hex_str), 4):
            if i + 4 <= len(hex_str):
                word = hex_str[i:i+4]
                # Swap bytes
                swapped = word[2:4] + word[0:2]
                try:
                    val = int(swapped, 16)
                    if val <= 9999:
                        little_endian_bcd += f"{val:04d}".lstrip('0') or '0'
                except:
                    continue

        methods.append(("Little-Endian BCD", little_endian_bcd))

        # Choose the best method (longest valid digit sequence)
        valid_results = [(name, result) for name, result in methods
                        if result and result.isdigit() and len(result) >= 8]

        if valid_results:
            best_method, best_result = max(valid_results, key=lambda x: len(x[1]))
            return best_result

        # Fallback: longest digit sequence without minimum length
        all_results = [(name, result) for name, result in methods if result and result.isdigit()]
        if all_results:
            fallback_method, fallback_result = max(all_results, key=lambda x: len(x[1]))
            return fallback_result

        return ""

    except Exception:
        return ""

def process_girocard_afl_records(connection, gpo_hex):
    """
    Process girocard AFL (Application File Locator) records.
    Extracts PAN and expiry from record data.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Find AFL tag (94) in GPO response
        if '94' not in gpo_hex:
            return False

        idx = gpo_hex.find('94')
        if idx + 4 > len(gpo_hex):
            return False

        length = int(gpo_hex[idx+2:idx+4], 16)
        if length == 0 or idx + 4 + length * 2 > len(gpo_hex):
            return False

        afl_data = gpo_hex[idx+4:idx+4+length*2]
        logger.debug(f"AFL data: {afl_data}")

        # Parse AFL entries (each entry is 4 bytes)
        for i in range(0, len(afl_data), 8):
            if i + 8 > len(afl_data):
                break

            sfi = int(afl_data[i:i+2], 16) >> 3
            first_record = int(afl_data[i+2:i+4], 16)
            last_record = int(afl_data[i+4:i+6], 16)
            num_records_offline = int(afl_data[i+6:i+8], 16)

            logger.debug(f"AFL: SFI={sfi}, Records={first_record}-{last_record}")

            # Read records from SFI
            for record_num in range(first_record, last_record + 1):
                try:
                    read_cmd = [0x00, 0xB2, record_num, (sfi << 3) | 0x04, 0x00]
                    resp, sw1, sw2 = connection.transmit(read_cmd)

                    if sw1 == 0x90:
                        # Import parse_apdu locally to avoid circular import
                        from app.nfc_reader import parse_apdu, comprehensive_card_type_detection, handle_card_scan

                        pan, expiry = parse_apdu(resp)
                        if pan and len(pan) >= 13:
                            card_type = comprehensive_card_type_detection(pan)
                            logger.info(f"Girocard via AFL: PAN={pan}, Expiry={expiry}, Type={card_type}")
                            handle_card_scan((pan, expiry))
                            return True
                except Exception as e:
                    logger.debug(f"AFL record read error: {e}")
                    continue

        return False

    except Exception as e:
        logger.debug(f"AFL processing error: {e}")
        return False

# Export for validate_luhn compatibility
validate_luhn = enhanced_luhn_validation
