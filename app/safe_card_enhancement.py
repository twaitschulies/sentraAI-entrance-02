"""
Safe Card Enhancement Wrapper
==============================
Sichere Integration der erweiterten Kartenerkennung ohne Beeinträchtigung
bestehender Funktionen. Fallback auf Original-Verhalten bei Fehlern.
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Import der erweiterten Erkennung - JETZT UNIVERSAL
try:
    from .universal_enhanced_recognition import (
        universal_card_enhancement,
        analyze_pse_ppse_response,
        analyze_aid_responses,
        identify_card_type_universal,
        get_supported_card_types
    )
    ENHANCED_RECOGNITION_AVAILABLE = True
    logger.info("✅ Universal Enhanced Card Recognition geladen")
except ImportError:
    try:
        # Fallback auf alte Module
        from .enhanced_card_recognition import (
            enhanced_visa_recognition as universal_card_enhancement,
            analyze_pse_response as analyze_pse_ppse_response,
            analyze_aid_failures as analyze_aid_responses,
            extract_pan_from_pse_data,
            create_learning_data
        )
        ENHANCED_RECOGNITION_AVAILABLE = True
        logger.info("✅ Enhanced Card Recognition (Legacy) geladen")
    except ImportError as e:
        ENHANCED_RECOGNITION_AVAILABLE = False
        logger.warning(f"Card Recognition Module nicht verfügbar: {e}")
        
        # Fallback-Funktionen
        def universal_card_enhancement(pan, raw_data, card_type):
            return {'enhanced': False, 'final_pan': pan, 'final_type': card_type}
        
        def extract_pan_from_pse_data(raw_data):
            return None

        def create_learning_data(enhancement):
            return {'learning_available': False}

# Import für sicheres Logging
try:
    from .safe_logging import safe_log_fallback
    SAFE_LOGGING_AVAILABLE = True
except ImportError:
    SAFE_LOGGING_AVAILABLE = False
    def safe_log_fallback(raw_data, error_type):
        pass

def safe_enhance_card_scan(
    pan: str, 
    raw_data: str, 
    card_type: str,
    scan_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Sichere Hauptfunktion zur erweiterten Kartenerkennung.
    Fällt bei Fehlern graceful auf Original-Werte zurück.
    """
    # Basis-Ergebnis (Fallback)
    result = {
        'success': True,
        'enhanced': False,
        'original_pan': pan,
        'original_type': card_type,
        'final_pan': pan,
        'final_type': card_type,
        'confidence': 50,  # Standard-Konfidenz für unveränderte Karten
        'auto_approve': False,
        'enhancement_notes': [],
        'fallback_reason': None
    }
    
    try:
        if not ENHANCED_RECOGNITION_AVAILABLE:
            result['fallback_reason'] = 'Enhanced recognition not available'
            return result
        
        # Versuche universelle erweiterte Erkennung
        enhancement = universal_card_enhancement(pan, raw_data or '', card_type)
        
        if enhancement.get('enhanced'):
            result['enhanced'] = True
            result['final_pan'] = enhancement.get('final_pan', enhancement.get('new_pan', pan))
            result['final_type'] = enhancement.get('final_type', enhancement.get('new_type', card_type))
            result['confidence'] = enhancement.get('confidence', 50)
            result['auto_approve'] = enhancement.get('auto_approve', False)
            result['enhancement_notes'] = enhancement.get('reasons', [])
            
            # Logging für erfolgreiche Enhancement
            logger.info(f"🎯 Card Enhanced: {card_type} → {result['final_type']} "
                       f"(Konfidenz: {result['confidence']}%)")
            
            if result['auto_approve']:
                logger.warning(f"✅ Auto-Approval: {result['final_pan'][:6] if result['final_pan'] else 'Unknown'}...****")
        
        # Lern-Daten erstellen (deaktiviert - Funktion nicht verfügbar)
        # if enhancement:
        #     learning_data = create_learning_data(enhancement)
        #     result['learning_data'] = learning_data
        
        return result
        
    except Exception as e:
        logger.error(f"Enhanced card recognition failed, using fallback: {e}")
        result['fallback_reason'] = f"Enhancement error: {str(e)}"
        result['success'] = False
        return result

def safe_extract_pan_from_logs(raw_data: str) -> Optional[str]:
    """
    Sichere PAN-Extraktion aus Log-Daten.
    """
    try:
        if not ENHANCED_RECOGNITION_AVAILABLE or not raw_data:
            return None
        
        extracted_pan = extract_pan_from_pse_data(raw_data)
        
        if extracted_pan:
            logger.info(f"🔍 PAN extracted from logs: {extracted_pan[:6]}...{extracted_pan[-4:]}")
            return extracted_pan
        
        return None
        
    except Exception as e:
        logger.debug(f"PAN extraction from logs failed: {e}")
        return None

def should_auto_approve_card(enhancement_result: Dict[str, Any]) -> bool:
    """
    Sichere Prüfung ob eine Karte automatisch genehmigt werden soll.
    """
    try:
        if not enhancement_result.get('enhanced'):
            return False
        
        auto_approve = enhancement_result.get('auto_approve', False)
        confidence = enhancement_result.get('confidence', 0)
        
        # Zusätzliche Sicherheitsprüfungen
        if auto_approve and confidence >= 60:
            logger.warning(f"🚨 Auto-Approval recommended (Confidence: {confidence}%)")
            return True
        
        return False
        
    except Exception as e:
        logger.debug(f"Auto-approval check failed: {e}")
        return False

def log_card_recognition_attempt(
    pan: str,
    raw_data: str,
    card_type: str,
    enhancement_result: Dict[str, Any],
    success: bool = False
) -> bool:
    """
    Sicheres Logging von Kartenerkennungsversuchen.
    """
    try:
        if not SAFE_LOGGING_AVAILABLE:
            return False
        
        # Erstelle strukturierte Log-Nachricht
        log_data = {
            'pan_masked': f"{pan[:6]}...{pan[-4:]}" if pan and len(pan) >= 10 else pan,
            'original_type': card_type,
            'enhanced': enhancement_result.get('enhanced', False),
            'final_type': enhancement_result.get('final_type', card_type),
            'confidence': enhancement_result.get('confidence', 0),
            'auto_approve': enhancement_result.get('auto_approve', False),
            'success': success
        }
        
        error_type = 'card_recognition_enhanced' if enhancement_result.get('enhanced') else 'card_recognition_standard'
        
        return safe_log_fallback(
            f"Enhanced Card Recognition: {json.dumps(log_data, indent=2)}\n\nRaw Data:\n{raw_data[:500]}",
            error_type
        )
        
    except Exception as e:
        logger.debug(f"Card recognition logging failed: {e}")
        return False

def get_enhancement_statistics() -> Dict[str, Any]:
    """
    Statistiken über die Kartenverbesserungen.
    """
    try:
        stats = {
            'enhanced_recognition_available': ENHANCED_RECOGNITION_AVAILABLE,
            'safe_logging_available': SAFE_LOGGING_AVAILABLE,
            'supported_enhancements': []
        }
        
        if ENHANCED_RECOGNITION_AVAILABLE:
            from .enhanced_card_recognition import ENHANCED_VISA_PATTERNS
            stats['supported_enhancements'] = list(ENHANCED_VISA_PATTERNS.keys())
        
        return stats
        
    except Exception as e:
        return {'error': str(e)}

# Wrapper-Funktion für bestehende NFC-Reader Integration
def enhance_nfc_card_data(
    original_pan: str,
    original_expiry: str,
    raw_apdu_data: str,
    card_type: str = 'unknown'
) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    Hauptfunktion für NFC-Reader Integration.
    
    Returns:
        Tuple[pan, expiry, card_type, enhancement_info]
    """
    try:
        # Versuche Kartenverbesserung
        enhancement = safe_enhance_card_scan(
            pan=original_pan,
            raw_data=raw_apdu_data,
            card_type=card_type
        )
        
        final_pan = enhancement['final_pan']
        final_type = enhancement['final_type']
        
        # Falls keine PAN gefunden, versuche Extraktion
        if not final_pan:
            extracted_pan = safe_extract_pan_from_logs(raw_apdu_data)
            if extracted_pan:
                final_pan = extracted_pan
                enhancement['final_pan'] = extracted_pan
                enhancement['enhancement_notes'].append('PAN aus Rohdaten extrahiert')
        
        return final_pan, original_expiry, final_type, enhancement
        
    except Exception as e:
        logger.error(f"NFC card enhancement failed: {e}")
        return original_pan, original_expiry, card_type, {'error': str(e)}

# Export der wichtigsten Funktionen
__all__ = [
    'safe_enhance_card_scan',
    'safe_extract_pan_from_logs',
    'should_auto_approve_card',
    'log_card_recognition_attempt',
    'get_enhancement_statistics',
    'enhance_nfc_card_data',
    'ENHANCED_RECOGNITION_AVAILABLE'
]

# Test beim direkten Aufruf
if __name__ == "__main__":
    print("🧪 Safe Card Enhancement Tests")
    print("=" * 50)
    
    # Test mit problematischer Visa-Karte
    test_raw_data = """
    german_contactless_pse    OK
    9000    
    select_german_aid_A0000001523010    Fehler
    6A82    
    PAN: 4220560000002044
    """
    
    pan, expiry, card_type, enhancement = enhance_nfc_card_data(
        original_pan='4220560000002044',
        original_expiry='12/28',
        raw_apdu_data=test_raw_data,
        card_type='unknown_card'
    )
    
    print(f"Original PAN: 4220560000002044")
    print(f"Final PAN: {pan}")
    print(f"Card Type: {card_type}")
    print(f"Enhanced: {'✅' if enhancement.get('enhanced') else '❌'}")
    print(f"Auto-Approve: {'✅' if enhancement.get('auto_approve') else '❌'}")
    print(f"Confidence: {enhancement.get('confidence', 0)}%")
    
    stats = get_enhancement_statistics()
    print(f"\nEnhancement Status: {stats}")
    
    print("\n✅ Tests completed")