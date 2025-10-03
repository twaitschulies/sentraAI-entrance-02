"""
Universal Enhanced Card Recognition
====================================
Verbesserte Kartenerkennung für ALLE Kartentypen:
- Visa, Mastercard, Maestro, American Express
- Girocard, EC-Karte, V-Pay
- JCB, Diners Club, Discover
Mit PSE/PPSE-Unterstützung und AID-Fehlerbehandlung
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Erweiterte Karten-Pattern-Datenbank für ALLE Kartentypen
UNIVERSAL_CARD_PATTERNS = {
    # VISA
    'visa': {
        'prefixes': ['4'],
        'lengths': [13, 16, 19],
        'name': 'Visa',
        'aids': ['A0000000031010', 'A0000000032010', 'A0000000038010'],
        'pse_required': False
    },
    
    # MASTERCARD
    'mastercard': {
        'prefixes': ['51', '52', '53', '54', '55', '2221-2720'],
        'lengths': [16],
        'name': 'Mastercard',
        'aids': ['A0000000041010', 'A0000000043060', 'A0000000046000'],
        'pse_required': False
    },
    
    # MAESTRO
    'maestro': {
        'prefixes': ['5018', '5020', '5038', '5893', '6304', '6759', '6761', '6762', '6763'],
        'lengths': [12, 13, 14, 15, 16, 17, 18, 19],
        'name': 'Maestro',
        'aids': ['A0000000043060'],
        'pse_required': False
    },
    
    # AMERICAN EXPRESS
    'amex': {
        'prefixes': ['34', '37'],
        'lengths': [15],
        'name': 'American Express',
        'aids': ['A00000002501'],
        'pse_required': False
    },
    
    # GIROCARD (Deutsche EC-Karte)
    'girocard': {
        'prefixes': ['672', '673', '674', '675', '676', '677', '678', '679'],
        'lengths': [16, 17, 18, 19],
        'name': 'Girocard',
        'aids': ['A0000003591010028001', 'D27600002545500200'],
        'pse_required': True  # Oft PSE-basiert
    },
    
    # V-PAY
    'vpay': {
        'prefixes': ['4'],  # Visa-basiert
        'lengths': [16],
        'name': 'V-Pay',
        'aids': ['A0000000032010'],
        'pse_required': True
    },
    
    # JCB
    'jcb': {
        'prefixes': ['3528-3589'],
        'lengths': [16],
        'name': 'JCB',
        'aids': ['A0000000651010'],
        'pse_required': False
    },
    
    # DINERS CLUB
    'diners': {
        'prefixes': ['36', '38', '300-305'],
        'lengths': [14],
        'name': 'Diners Club',
        'aids': ['A0000001523010'],
        'pse_required': False
    },
    
    # DISCOVER
    'discover': {
        'prefixes': ['6011', '644-649', '65', '622126-622925'],
        'lengths': [16],
        'name': 'Discover',
        'aids': ['A0000001524010'],
        'pse_required': False
    }
}

# Bekannte problematische Karten mit spezieller Behandlung
PROBLEMATIC_CARDS = {
    '422056': {
        'type': 'visa',
        'name': 'Visa Debit (Problematisch)',
        'pse_success_expected': True,
        'aid_failures_expected': ['A0000001523010', 'D27600002545500200'],
        'auto_approve': True,
        'confidence_boost': 40
    },
    '444952': {
        'type': 'visa',
        'name': 'Visa (Problematisch)',
        'pse_success_expected': True,
        'aid_failures_expected': ['A0000001523010'],
        'auto_approve': True,
        'confidence_boost': 35
    },
    '537228': {  # Beispiel Mastercard
        'type': 'mastercard',
        'name': 'Mastercard Debit',
        'pse_success_expected': True,
        'aid_failures_expected': [],
        'auto_approve': False,
        'confidence_boost': 20
    }
}

def analyze_pse_ppse_response(raw_data: str) -> Dict[str, Any]:
    """
    Analysiert PSE (Payment System Environment) und PPSE (Proximity PSE) Responses.
    Funktioniert für alle Kartentypen.
    """
    analysis = {
        'pse_success': False,
        'ppse_success': False,
        'supported_applications': [],
        'card_capabilities': [],
        'confidence': 0
    }
    
    try:
        # PSE-Patterns (2PAY.SYS.DDF01)
        pse_patterns = [
            r'german_contactless_pse\s+OK\s+9000',
            r'32 50 41 59 2E 53 59 53 2E 44 44 46 30 31',  # 2PAY.SYS.DDF01 in hex
            r'6F.*84.*32 50 41 59',  # PSE in TLV
            r'SELECT.*2PAY.*SUCCESS',
        ]
        
        # PPSE-Patterns (kontaktlos)
        ppse_patterns = [
            r'2PAY\.SYS\.DDF01',
            r'325041592E5359532E4444463031',
            r'ppse.*success',
            r'contactless.*ok'
        ]
        
        # Prüfe PSE
        for pattern in pse_patterns:
            if re.search(pattern, raw_data, re.IGNORECASE):
                analysis['pse_success'] = True
                analysis['confidence'] += 25
                logger.debug("✅ PSE erfolgreich erkannt")
                break
        
        # Prüfe PPSE
        for pattern in ppse_patterns:
            if re.search(pattern, raw_data, re.IGNORECASE):
                analysis['ppse_success'] = True
                analysis['confidence'] += 20
                analysis['card_capabilities'].append('contactless')
                logger.debug("✅ PPSE (kontaktlos) erkannt")
                break
        
        # Extrahiere unterstützte Anwendungen aus PSE-Response
        aid_pattern = r'A0[0-9A-F]{10,30}'
        aids = re.findall(aid_pattern, raw_data.upper())
        for aid in aids:
            analysis['supported_applications'].append(aid)
            analysis['confidence'] += 5
        
        # Kartentyp-Hinweise aus PSE-Daten
        if 'VISA' in raw_data.upper():
            analysis['card_capabilities'].append('visa_capable')
        if 'MASTERCARD' in raw_data.upper() or 'MAESTRO' in raw_data.upper():
            analysis['card_capabilities'].append('mastercard_capable')
        if 'GIROCARD' in raw_data.upper() or 'ELECTRONIC CASH' in raw_data.upper():
            analysis['card_capabilities'].append('girocard_capable')
        
        return analysis
        
    except Exception as e:
        logger.debug(f"PSE/PPSE-Analyse fehlgeschlagen: {e}")
        return analysis

def identify_card_type_universal(pan: str, raw_data: str = "") -> Tuple[str, int]:
    """
    Universelle Kartentyp-Identifikation für alle Kartentypen.
    Returns: (card_type, confidence)
    """
    if not pan or not pan.isdigit():
        return 'unknown', 0
    
    # Prüfe problematische Karten zuerst
    for prefix, info in PROBLEMATIC_CARDS.items():
        if pan.startswith(prefix):
            logger.info(f"🎯 Bekannte problematische Karte erkannt: {info['name']}")
            return info['type'], 80 + info.get('confidence_boost', 0)
    
    # Prüfe Standard-Patterns
    for card_type, info in UNIVERSAL_CARD_PATTERNS.items():
        for prefix in info['prefixes']:
            # Range-Check (z.B. "2221-2720")
            if '-' in prefix:
                start, end = prefix.split('-')
                if len(pan) >= len(start):
                    pan_prefix = int(pan[:len(start)])
                    if int(start) <= pan_prefix <= int(end):
                        if len(pan) in info['lengths']:
                            return card_type, 70
            # Direkter Prefix-Check
            elif pan.startswith(prefix):
                if len(pan) in info['lengths']:
                    return card_type, 75
    
    # Fallback basierend auf erster Ziffer
    first_digit = pan[0]
    fallbacks = {
        '4': ('visa', 50),
        '5': ('mastercard', 45),
        '6': ('maestro', 40),
        '3': ('amex', 35)
    }
    
    if first_digit in fallbacks:
        return fallbacks[first_digit]
    
    return 'unknown', 10

def analyze_aid_responses(raw_data: str) -> Dict[str, Any]:
    """
    Analysiert AID-Responses für alle Kartentypen.
    """
    analysis = {
        'successful_aids': [],
        'failed_aids': [],
        'error_codes': {},
        'card_hints': []
    }
    
    try:
        # Erfolgreiche AID-Selektionen
        success_pattern = r'select.*aid.*([A-F0-9]{10,30}).*(?:OK|9000|success)'
        successes = re.findall(success_pattern, raw_data, re.IGNORECASE)
        analysis['successful_aids'] = list(set(successes))
        
        # Fehlgeschlagene AID-Selektionen mit Fehlercode
        failure_pattern = r'select.*aid.*([A-F0-9]{10,30}).*(?:Fehler|error|failed).*([6-9A-F][0-9A-F]{3})'
        failures = re.findall(failure_pattern, raw_data, re.IGNORECASE)
        
        for aid, error_code in failures:
            analysis['failed_aids'].append(aid)
            analysis['error_codes'][aid] = error_code
            
            # Interpretiere Fehlercodes
            if error_code == '6A82':
                analysis['card_hints'].append(f"AID {aid[:10]}... nicht unterstützt (normal für manche Karten)")
            elif error_code == '6985':
                analysis['card_hints'].append(f"Bedingungen nicht erfüllt für {aid[:10]}...")
            elif error_code == '6D00':
                analysis['card_hints'].append(f"Instruktion nicht unterstützt für {aid[:10]}...")
        
        # Erkenne Kartentyp aus erfolgreichen AIDs
        for aid in analysis['successful_aids']:
            for card_type, info in UNIVERSAL_CARD_PATTERNS.items():
                if any(aid.startswith(known_aid) for known_aid in info['aids']):
                    analysis['card_hints'].append(f"Wahrscheinlich {info['name']}")
                    break
        
        return analysis
        
    except Exception as e:
        logger.debug(f"AID-Analyse fehlgeschlagen: {e}")
        return analysis

def universal_card_enhancement(
    pan: str,
    raw_data: str,
    original_type: str
) -> Dict[str, Any]:
    """
    Universelle Kartenverbesserung für ALLE Kartentypen.
    """
    result = {
        'enhanced': False,
        'original_pan': pan,
        'original_type': original_type,
        'final_pan': pan,
        'final_type': original_type,
        'confidence': 0,
        'auto_approve': False,
        'analysis': {},
        'recommendations': [],
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # PSE/PPSE-Analyse
        pse_analysis = analyze_pse_ppse_response(raw_data)
        result['analysis']['pse'] = pse_analysis
        result['confidence'] += pse_analysis['confidence']
        
        # AID-Analyse
        aid_analysis = analyze_aid_responses(raw_data)
        result['analysis']['aid'] = aid_analysis
        
        # Kartentyp-Identifikation
        if pan:
            card_type, type_confidence = identify_card_type_universal(pan, raw_data)
            result['confidence'] += type_confidence
            
            if card_type != 'unknown':
                result['final_type'] = card_type
                result['enhanced'] = True
                
                # Hole Karteninfo
                card_info = UNIVERSAL_CARD_PATTERNS.get(card_type, {})
                result['final_type'] = card_info.get('name', card_type)
                
                # Prüfe ob es eine problematische Karte ist
                for prefix, prob_info in PROBLEMATIC_CARDS.items():
                    if pan.startswith(prefix):
                        result['auto_approve'] = prob_info.get('auto_approve', False)
                        result['confidence'] += prob_info.get('confidence_boost', 0)
                        result['recommendations'].append(f"Bekannte Karte: {prob_info['name']}")
                        
                        # Validiere erwartete Fehlermuster
                        if prob_info.get('pse_success_expected') and pse_analysis['pse_success']:
                            result['confidence'] += 15
                            result['recommendations'].append("PSE-Erfolg wie erwartet")
                        
                        expected_failures = prob_info.get('aid_failures_expected', [])
                        for aid in expected_failures:
                            if aid in aid_analysis['failed_aids']:
                                result['confidence'] += 10
                                result['recommendations'].append(f"Erwarteter AID-Fehler: {aid[:10]}...")
                        break
        
        # Generelle Empfehlungen basierend auf Analyse
        if pse_analysis['pse_success'] and not aid_analysis['successful_aids']:
            result['recommendations'].append("PSE erfolgreich aber keine AIDs - typisch für moderne Karten")
            result['confidence'] += 10
        
        if pse_analysis['ppse_success']:
            result['recommendations'].append("Kontaktlose Funktion verfügbar")
            result['confidence'] += 5
        
        # Finale Bewertung
        if result['confidence'] >= 80:
            result['status'] = 'high_confidence'
            if result['confidence'] >= 90:
                result['auto_approve'] = True
        elif result['confidence'] >= 50:
            result['status'] = 'medium_confidence'
        else:
            result['status'] = 'low_confidence'
        
        # Log-Ausgabe für Monitoring
        if result['enhanced']:
            logger.info(f"🎯 Universelle Kartenerkennung: {original_type} → {result['final_type']} "
                       f"(Konfidenz: {result['confidence']}%, Status: {result['status']})")
        
        return result
        
    except Exception as e:
        logger.error(f"Universelle Kartenerkennung fehlgeschlagen: {e}")
        result['error'] = str(e)
        return result

def get_supported_card_types() -> List[Dict[str, Any]]:
    """
    Gibt Liste aller unterstützten Kartentypen zurück.
    """
    supported = []
    for card_type, info in UNIVERSAL_CARD_PATTERNS.items():
        supported.append({
            'type': card_type,
            'name': info['name'],
            'prefixes': info['prefixes'][:3],  # Erste 3 Präfixe
            'lengths': info['lengths'],
            'pse_required': info.get('pse_required', False)
        })
    return supported

# Test-Funktionen
if __name__ == "__main__":
    print("🧪 Universal Card Recognition Tests")
    print("=" * 60)
    
    test_cases = [
        {'pan': '4220560000002044', 'type': 'Visa (Problematisch)'},
        {'pan': '5372288697116366', 'type': 'Mastercard'},
        {'pan': '6759123456789012', 'type': 'Maestro'},
        {'pan': '371234567890123', 'type': 'American Express'},
        {'pan': '6729123456789012', 'type': 'Girocard'},
        {'pan': '3528123456789012', 'type': 'JCB'},
    ]
    
    for test in test_cases:
        card_type, confidence = identify_card_type_universal(test['pan'])
        card_info = UNIVERSAL_CARD_PATTERNS.get(card_type, {})
        print(f"PAN: {test['pan']}")
        print(f"  Erwartet: {test['type']}")
        print(f"  Erkannt: {card_info.get('name', card_type)}")
        print(f"  Konfidenz: {confidence}%")
        print(f"  Status: {'✅' if confidence > 50 else '⚠️'}\n")
    
    print("\nUnterstützte Kartentypen:")
    for card in get_supported_card_types():
        print(f"  • {card['name']} (Präfixe: {', '.join(card['prefixes'])})")
    
    print("\n✅ Tests abgeschlossen")