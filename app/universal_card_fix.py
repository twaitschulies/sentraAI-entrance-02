"""
Universal Card Fix Module
=========================
Universelles Modul zur Verbesserung der Kartenerkennung für ALLE Kartentypen.
Sammelt Daten über nicht erkannte Karten zur nachträglichen Analyse.
"""

import logging
import re
import json
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Bekannte Kartenpräfixe und ihre Typen (erweiterbar)
CARD_PREFIXES = {
    # Visa
    '4': {'type': 'visa', 'name': 'Visa', 'min_length': 13, 'max_length': 19},
    
    # Mastercard
    '51': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '52': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '53': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '54': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '55': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '2221': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    '2720': {'type': 'mastercard', 'name': 'Mastercard', 'min_length': 16, 'max_length': 16},
    
    # Maestro
    '5018': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '5020': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '5038': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '6304': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '6759': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '6761': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '6762': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    '6763': {'type': 'maestro', 'name': 'Maestro', 'min_length': 12, 'max_length': 19},
    
    # American Express
    '34': {'type': 'amex', 'name': 'American Express', 'min_length': 15, 'max_length': 15},
    '37': {'type': 'amex', 'name': 'American Express', 'min_length': 15, 'max_length': 15},
    
    # Girocard (Deutschland)
    '6729': {'type': 'girocard', 'name': 'Girocard', 'min_length': 16, 'max_length': 19},
    
    # Spezielle problematische Karten
    '422056': {'type': 'visa_debit', 'name': 'Visa Debit Special', 'min_length': 16, 'max_length': 16, 'auto_approve': True},
    '444952': {'type': 'visa_credit', 'name': 'Visa Credit Special', 'min_length': 16, 'max_length': 16, 'auto_approve': True},
}

# APDU-Fehlercodes und ihre Bedeutungen
APDU_ERROR_CODES = {
    '6A82': 'File or application not found',
    '6A81': 'Function not supported',
    '6982': 'Security condition not satisfied',
    '6985': 'Conditions of use not satisfied',
    '6D00': 'Instruction code not supported',
    '6E00': 'Class not supported',
    '9000': 'Success',
    '61XX': 'More data available',
    '6CXX': 'Wrong length',
}

def extract_pan_from_raw_data(raw_data: str) -> List[Dict[str, Any]]:
    """
    Extrahiert mögliche PANs aus Rohdaten mit verschiedenen Methoden.
    Gibt eine Liste von Kandidaten mit Konfidenzwerten zurück.
    """
    if not raw_data:
        return []
    
    candidates = []
    cleaned = raw_data.upper().replace(' ', '').replace('\n', '')
    
    # Methode 1: Direkte numerische Sequenzen (13-19 Ziffern)
    numeric_pattern = r'\b(\d{13,19})\b'
    for match in re.finditer(numeric_pattern, cleaned):
        pan = match.group(1)
        candidates.append({
            'pan': pan,
            'method': 'direct_numeric',
            'confidence': 70,
            'position': match.start()
        })
    
    # Methode 2: EMV Tags (5A, 57, 9F6B)
    emv_patterns = [
        (r'5A([0-9A-F]{2})([0-9A-F]+)', 'tag_5A'),
        (r'57([0-9A-F]{2})([0-9A-F]+)', 'tag_57'),
        (r'9F6B([0-9A-F]{2})([0-9A-F]+)', 'tag_9F6B'),
    ]
    
    for pattern, method in emv_patterns:
        for match in re.finditer(pattern, cleaned):
            try:
                length = int(match.group(1), 16)
                data = match.group(2)[:length*2]
                
                # Dekodiere BCD oder extrahiere vor D-Separator
                if 'D' in data:
                    pan = data.split('D')[0].replace('F', '')
                else:
                    pan = data.replace('F', '')
                
                if pan.isdigit() and 13 <= len(pan) <= 19:
                    candidates.append({
                        'pan': pan,
                        'method': method,
                        'confidence': 85,
                        'position': match.start()
                    })
            except:
                continue
    
    # Methode 3: Track2-Daten
    track2_pattern = r'([0-9]{13,19})D'
    for match in re.finditer(track2_pattern, cleaned):
        pan = match.group(1)
        candidates.append({
            'pan': pan,
            'method': 'track2',
            'confidence': 90,
            'position': match.start()
        })
    
    # Methode 4: Mit Separatoren
    separator_patterns = [
        r'PAN[:\s]*([0-9]{13,19})',
        r'CARD[:\s]*([0-9]{13,19})',
        r'NUMBER[:\s]*([0-9]{13,19})',
    ]
    
    for pattern in separator_patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            pan = match.group(1)
            candidates.append({
                'pan': pan,
                'method': 'labeled',
                'confidence': 80,
                'position': match.start()
            })
    
    # Deduplizierung und Sortierung nach Konfidenz
    seen_pans = set()
    unique_candidates = []
    for candidate in sorted(candidates, key=lambda x: x['confidence'], reverse=True):
        if candidate['pan'] not in seen_pans:
            seen_pans.add(candidate['pan'])
            unique_candidates.append(candidate)
    
    return unique_candidates

def identify_card_type(pan: str) -> Dict[str, Any]:
    """
    Identifiziert den Kartentyp basierend auf der PAN.
    Unterstützt alle gängigen Kartentypen.
    """
    if not pan or not pan.isdigit():
        return {'type': 'unknown', 'name': 'Unknown', 'confidence': 0}
    
    # Prüfe längste Präfixe zuerst
    for prefix_len in [6, 4, 2, 1]:
        if len(pan) >= prefix_len:
            prefix = pan[:prefix_len]
            if prefix in CARD_PREFIXES:
                info = CARD_PREFIXES[prefix]
                # Längenvalidierung
                if info['min_length'] <= len(pan) <= info['max_length']:
                    return {
                        'type': info['type'],
                        'name': info['name'],
                        'confidence': 90,
                        'auto_approve': info.get('auto_approve', False),
                        'prefix_matched': prefix
                    }
    
    # Fallback-Erkennung basierend auf erster Ziffer
    first_digit = pan[0]
    general_types = {
        '4': 'visa',
        '5': 'mastercard',
        '6': 'discover',
        '3': 'amex_diners',
    }
    
    if first_digit in general_types:
        return {
            'type': f'{general_types[first_digit]}_generic',
            'name': f'{general_types[first_digit].title()} (Generic)',
            'confidence': 50,
            'prefix_matched': first_digit
        }
    
    return {'type': 'unknown', 'name': 'Unknown', 'confidence': 0}

def analyze_apdu_errors(raw_data: str) -> Dict[str, Any]:
    """
    Analysiert APDU-Fehlercodes in den Rohdaten.
    """
    errors_found = []
    suggestions = []
    
    for code, meaning in APDU_ERROR_CODES.items():
        if code in raw_data.upper():
            errors_found.append({
                'code': code,
                'meaning': meaning
            })
            
            # Spezifische Vorschläge basierend auf Fehlercode
            if code == '6A82':
                suggestions.append('Karte unterstützt möglicherweise kein Standard-EMV')
                suggestions.append('Alternative AIDs versuchen')
            elif code == '6982':
                suggestions.append('PIN-Verifizierung könnte erforderlich sein')
            elif code == '6985':
                suggestions.append('Karte ist möglicherweise gesperrt oder inaktiv')
    
    return {
        'errors': errors_found,
        'suggestions': suggestions,
        'has_errors': len(errors_found) > 0
    }

def enhanced_luhn_check(pan: str) -> bool:
    """
    Erweiterte Luhn-Prüfung mit Fehlertoleranz.
    """
    if not pan or not pan.isdigit():
        return False
    
    try:
        digits = [int(d) for d in pan]
        checksum = 0
        is_even = False
        
        for digit in reversed(digits):
            if is_even:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
            is_even = not is_even
        
        return checksum % 10 == 0
    except:
        return False

def universal_card_recognition(pan: str, raw_data: str, current_type: str) -> Dict[str, Any]:
    """
    Universelle Kartenerkennung mit Fallback-Mechanismen.
    """
    result = {
        'original_pan': pan,
        'original_type': current_type,
        'recognized': False,
        'card_info': None,
        'confidence': 0,
        'extraction_methods': [],
        'apdu_analysis': None,
        'suggestions': [],
        'timestamp': datetime.now().isoformat()
    }
    
    # Versuche PAN-Extraktion wenn nicht vorhanden
    if not pan:
        candidates = extract_pan_from_raw_data(raw_data)
        if candidates:
            # Wähle Kandidat mit höchster Konfidenz
            best_candidate = candidates[0]
            pan = best_candidate['pan']
            result['extraction_methods'] = [c['method'] for c in candidates[:3]]
            result['pan_extracted'] = True
            result['pan'] = pan
            logger.info(f"PAN extrahiert via {best_candidate['method']}: {pan[:6]}...{pan[-4:]}")
    else:
        result['pan'] = pan
    
    # APDU-Fehleranalyse
    if raw_data:
        result['apdu_analysis'] = analyze_apdu_errors(raw_data)
    
    # Kartentyp-Identifikation
    if pan:
        card_info = identify_card_type(pan)
        result['card_info'] = card_info
        result['confidence'] = card_info['confidence']
        
        # Luhn-Prüfung
        luhn_valid = enhanced_luhn_check(pan)
        result['luhn_valid'] = luhn_valid
        
        if not luhn_valid:
            result['suggestions'].append('Luhn-Prüfung fehlgeschlagen - manuelle Überprüfung empfohlen')
            # Bei bekannten problematischen Karten trotzdem akzeptieren
            if card_info.get('auto_approve'):
                result['recognized'] = True
                result['confidence'] = max(70, card_info['confidence'])
                result['override_reason'] = 'Bekannte problematische Karte - Auto-Genehmigung'
        else:
            result['recognized'] = card_info['confidence'] > 50
        
        # Generiere spezifische Vorschläge
        if card_info['type'] == 'unknown':
            result['suggestions'].append(f'Unbekannter Kartentyp für Präfix {pan[:4]}')
            result['suggestions'].append('Manuelle Klassifizierung erforderlich')
        elif card_info['confidence'] < 70:
            result['suggestions'].append('Niedrige Erkennungskonfidenz - weitere Validierung empfohlen')
    
    # Kombiniere alle Vorschläge
    if result['apdu_analysis'] and result['apdu_analysis']['suggestions']:
        result['suggestions'].extend(result['apdu_analysis']['suggestions'])
    
    return result

def create_learning_entry(pan: str, raw_data: str, success: bool) -> Dict[str, Any]:
    """
    Erstellt einen Lern-Eintrag für zukünftige Verbesserungen.
    Diese Daten können zur kontinuierlichen Verbesserung des Systems genutzt werden.
    """
    entry = {
        'timestamp': datetime.now().isoformat(),
        'pan_prefix': pan[:6] if pan and len(pan) >= 6 else None,
        'pan_length': len(pan) if pan else 0,
        'success': success,
        'raw_data_sample': raw_data[:500] if raw_data else None,
        'extraction_possible': len(extract_pan_from_raw_data(raw_data)) > 0,
        'card_type_detected': identify_card_type(pan) if pan else None,
        'apdu_errors': analyze_apdu_errors(raw_data)['errors'] if raw_data else []
    }
    
    return entry

def get_card_recognition_stats(learning_entries: List[Dict]) -> Dict[str, Any]:
    """
    Generiert Statistiken aus Lern-Einträgen.
    """
    if not learning_entries:
        return {'total': 0, 'success_rate': 0}
    
    stats = {
        'total': len(learning_entries),
        'successful': sum(1 for e in learning_entries if e['success']),
        'failed': sum(1 for e in learning_entries if not e['success']),
        'success_rate': 0,
        'card_types': {},
        'common_errors': {},
        'extraction_methods_success': {}
    }
    
    stats['success_rate'] = (stats['successful'] / stats['total']) * 100 if stats['total'] > 0 else 0
    
    # Analysiere Kartentypen
    for entry in learning_entries:
        if entry.get('card_type_detected'):
            card_type = entry['card_type_detected'].get('type', 'unknown')
            stats['card_types'][card_type] = stats['card_types'].get(card_type, 0) + 1
    
    # Analysiere häufige Fehler
    for entry in learning_entries:
        for error in entry.get('apdu_errors', []):
            error_code = error['code']
            stats['common_errors'][error_code] = stats['common_errors'].get(error_code, 0) + 1
    
    return stats

# Test-Funktion
if __name__ == "__main__":
    test_cases = [
        {
            'pan': '4220560000002044',
            'raw_data': 'Error: 6A82',
            'type': 'unknown_card'
        },
        {
            'pan': '5372288697116366',
            'raw_data': '57 10 53 72 28 86 97 11 63 66 D2 80 32',
            'type': 'unknown'
        },
        {
            'pan': None,
            'raw_data': 'PAN: 4449520000002056, Response: 6A82',
            'type': 'unknown_german_failed'
        }
    ]
    
    print("Universal Card Recognition Tests")
    print("=" * 60)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        result = universal_card_recognition(test['pan'], test['raw_data'], test['type'])
        
        print(f"  PAN: {result.get('pan', 'Not found')}")
        if result['card_info']:
            print(f"  Card Type: {result['card_info']['name']} ({result['card_info']['type']})")
        print(f"  Confidence: {result['confidence']}%")
        print(f"  Recognized: {'✅' if result['recognized'] else '❌'}")
        
        if result['suggestions']:
            print(f"  Suggestions:")
            for suggestion in result['suggestions']:
                print(f"    - {suggestion}")