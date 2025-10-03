"""
NFC Reader Enhancement Module
==============================
Sichere Integration der universellen Kartenerkennung in den bestehenden NFC-Reader.
Dieses Modul erweitert die Funktionalität OHNE bestehende Features zu beeinträchtigen.
"""

import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Imports der neuen Module
try:
    from .universal_card_fix import (
        universal_card_recognition,
        extract_pan_from_raw_data,
        identify_card_type,
        enhanced_luhn_check
    )
    from .structured_fallback_log import (
        log_structured_fallback,
        create_structured_fallback_log
    )
    ENHANCED_MODULES_AVAILABLE = True
    logger.info("✅ Enhanced Card Recognition Module geladen")
except ImportError as e:
    ENHANCED_MODULES_AVAILABLE = False
    logger.warning(f"Enhanced Module nicht verfügbar: {e}")
    # Fallback-Funktionen
    def universal_card_recognition(*args, **kwargs):
        return {'recognized': False}
    def log_structured_fallback(*args, **kwargs):
        return False

def safe_enhance_card_recognition(pan: str, raw_data: str, card_type: str) -> Dict[str, Any]:
    """
    Sichere Wrapper-Funktion für die erweiterte Kartenerkennung.
    Fällt auf Original-Verhalten zurück bei Fehlern.
    """
    try:
        if not ENHANCED_MODULES_AVAILABLE:
            return {
                'enhanced': False,
                'pan': pan,
                'card_type': card_type,
                'confidence': 0
            }
        
        # Versuche universelle Erkennung
        result = universal_card_recognition(pan, raw_data, card_type)
        
        # Erstelle sicheres Rückgabe-Format
        enhanced_result = {
            'enhanced': True,
            'pan': result.get('pan', pan),
            'card_type': card_type,  # Behalte Original bei wenn nicht besser erkannt
            'confidence': result.get('confidence', 0),
            'suggestions': result.get('suggestions', []),
            'auto_approve': False
        }
        
        # Nur überschreiben wenn besser erkannt
        if result.get('recognized') and result.get('confidence', 0) > 60:
            if result.get('card_info'):
                enhanced_result['card_type'] = result['card_info'].get('type', card_type)
                enhanced_result['card_name'] = result['card_info'].get('name', '')
                enhanced_result['auto_approve'] = result['card_info'].get('auto_approve', False)
        
        return enhanced_result
        
    except Exception as e:
        logger.debug(f"Enhanced recognition failed, using fallback: {e}")
        return {
            'enhanced': False,
            'pan': pan,
            'card_type': card_type,
            'confidence': 0
        }

def safe_log_fallback(raw_data: str, error_type: str, pan: str = None) -> bool:
    """
    Sichere Wrapper-Funktion für strukturiertes Fallback-Logging.
    """
    try:
        if ENHANCED_MODULES_AVAILABLE:
            # Versuche strukturiertes Logging
            return log_structured_fallback(raw_data, error_type, pan)
        else:
            # Fallback zum Standard error_logger
            from app import error_logger
            return error_logger.log_fallback(raw_data, error_type)
    except Exception as e:
        logger.error(f"Structured logging failed: {e}")
        try:
            from app import error_logger
            return error_logger.log_fallback(raw_data, error_type)
        except:
            return False

def enhance_parse_apdu(original_function):
    """
    Decorator zur Erweiterung der parse_apdu Funktion.
    Fügt erweiterte Erkennung hinzu ohne Original zu verändern.
    """
    def wrapper(data):
        # Erst Original-Funktion ausführen
        pan, expiry = original_function(data)
        
        # Wenn PAN nicht gefunden, versuche erweiterte Extraktion
        if not pan and ENHANCED_MODULES_AVAILABLE:
            try:
                from smartcard.util import toHexString
                hexdata = toHexString(data).replace(" ", "")
                
                # Versuche PAN-Extraktion mit neuen Methoden
                candidates = extract_pan_from_raw_data(hexdata)
                if candidates:
                    best = candidates[0]
                    if enhanced_luhn_check(best['pan']):
                        pan = best['pan']
                        logger.info(f"🎯 Enhanced PAN extraction successful: {pan[:6]}...{pan[-4:]}")
            except Exception as e:
                logger.debug(f"Enhanced extraction failed: {e}")
        
        return pan, expiry
    
    return wrapper

def integrate_enhanced_recognition():
    """
    Hauptfunktion zur sicheren Integration der erweiterten Erkennung.
    Kann vom nfc_reader importiert und aufgerufen werden.
    """
    if not ENHANCED_MODULES_AVAILABLE:
        logger.warning("Enhanced modules not available, skipping integration")
        return False
    
    logger.info("🚀 Enhanced Card Recognition Integration aktiviert")
    logger.info("  - Universelle Kartenerkennung für alle Typen")
    logger.info("  - Strukturiertes Fallback-Logging")
    logger.info("  - Automatische Fehleranalyse und Lösungsvorschläge")
    
    return True

# Hilfsfunktionen für den nfc_reader

def should_auto_approve(pan: str, card_type: str) -> bool:
    """
    Prüft ob eine Karte automatisch genehmigt werden soll.
    """
    if not ENHANCED_MODULES_AVAILABLE:
        return False
    
    try:
        card_info = identify_card_type(pan)
        return card_info.get('auto_approve', False)
    except:
        return False

def get_card_confidence(pan: str, raw_data: str = "") -> int:
    """
    Berechnet Konfidenz für Kartenerkennung.
    """
    if not ENHANCED_MODULES_AVAILABLE:
        return 50
    
    try:
        result = universal_card_recognition(pan, raw_data, 'unknown')
        return result.get('confidence', 50)
    except:
        return 50

# Export der sicheren Funktionen
__all__ = [
    'safe_enhance_card_recognition',
    'safe_log_fallback',
    'enhance_parse_apdu',
    'integrate_enhanced_recognition',
    'should_auto_approve',
    'get_card_confidence',
    'ENHANCED_MODULES_AVAILABLE'
]