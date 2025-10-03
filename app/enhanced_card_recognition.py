"""
Enhanced Card Recognition Module
=================================
Erweiterte Kartenerkennung speziell für problematische Visa-Karten
mit PSE-erfolgreichen, aber AID-fehlgeschlagenen Scans.
"""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Erweiterte Visa-Karten-Patterns basierend auf neuen Logs
ENHANCED_VISA_PATTERNS = {
    '422056': {
        'name': 'Visa Debit 422056 (Neue Ausgabe)',
        'type': 'visa_debit_new',
        'auto_approve': True,
        'confidence_boost': 40,
        'special_handling': True,
        'pse_required': True,  # Benötigt PSE-Erfolg
        'aid_failures_expected': ['A0000001523010']  # Diese AIDs schlagen erwartungsgemäß fehl
    }
}

# PSE-Response-Pattern (2PAY.SYS.DDF01 erfolgreich)
PSE_SUCCESS_PATTERNS = [
    r'german_contactless_pse\s+OK\s+9000',
    r'32 50 41 59 2E 53 59 53 2E 44 44 46 30 31',  # 2PAY.SYS.DDF01 hex
    r'6F.*84.*32 50 41 59',  # PSE in TLV-Format
]

# Bekannte fehlschlagende AIDs mit 6A82
EXPECTED_AID_FAILURES = [
    'A0000001523010',  # Deutscher Standard-AID
    'D27600002545500200',  # Girocard-AID
]

def analyze_pse_response(raw_data: str) -> Dict[str, Any]:
    """
    Analysiert PSE-Responses für erweiterte Kartenerkennung.
    """
    analysis = {
        'pse_success': False,
        'pse_applications': [],
        'confidence': 0
    }
    
    try:
        # Prüfe auf PSE-Erfolg
        for pattern in PSE_SUCCESS_PATTERNS:
            if re.search(pattern, raw_data, re.IGNORECASE):
                analysis['pse_success'] = True
                analysis['confidence'] += 30
                logger.debug("✅ PSE-Erfolg erkannt")
                break
        
        # Extrahiere Anwendungen aus PSE-Response
        if analysis['pse_success']:
            # Suche nach Anwendungs-AIDs in der PSE-Response
            aid_pattern = r'([A-F0-9]{14,32})'  # Typische AID-Längen
            aids = re.findall(aid_pattern, raw_data.upper())
            
            for aid in aids:
                if len(aid) >= 14:  # Mindestlänge für gültige AID
                    analysis['pse_applications'].append(aid)
                    analysis['confidence'] += 10
        
        return analysis
        
    except Exception as e:
        logger.debug(f"PSE-Analyse fehlgeschlagen: {e}")
        return analysis

def analyze_aid_failures(raw_data: str) -> Dict[str, Any]:
    """
    Analysiert AID-Fehlschläge mit 6A82 Fehlercode.
    """
    analysis = {
        'aid_failures': [],
        'expected_failures': 0,
        'unexpected_failures': 0,
        'confidence_boost': 0
    }
    
    try:
        # Suche nach AID-Fehlern mit 6A82
        failure_pattern = r'select_german_aid_([A-F0-9]+)\s+Fehler\s+6A82'
        failures = re.findall(failure_pattern, raw_data, re.IGNORECASE)
        
        for failed_aid in failures:
            analysis['aid_failures'].append(failed_aid)
            
            if failed_aid in EXPECTED_AID_FAILURES:
                analysis['expected_failures'] += 1
                analysis['confidence_boost'] += 15  # Erwartete Fehler erhöhen Konfidenz
                logger.debug(f"✅ Erwarteter AID-Fehler: {failed_aid}")
            else:
                analysis['unexpected_failures'] += 1
                logger.warning(f"⚠️ Unerwarteter AID-Fehler: {failed_aid}")
        
        return analysis
        
    except Exception as e:
        logger.debug(f"AID-Fehler-Analyse fehlgeschlagen: {e}")
        return analysis

def extract_pan_from_pse_data(raw_data: str) -> Optional[str]:
    """
    Erweiterte PAN-Extraktion speziell für PSE-Daten.
    """
    try:
        # Verschiedene PAN-Extraktionsmuster für PSE-Daten
        pse_pan_patterns = [
            r'5A\s*08\s*([4-6][0-9A-F\s]{14,18})',  # Tag 5A in PSE
            r'57\s*[0-9A-F]{2}\s*([4-6][0-9A-F\s]{14,18})D',  # Track2 in PSE
            r'PAN[:\s]*([4-6]\d{15})',  # Direkte PAN-Angabe
            r'([4-6]\d{15})',  # Generisches 16-stelliges Pattern
        ]
        
        for pattern in pse_pan_patterns:
            matches = re.findall(pattern, raw_data.upper().replace(' ', ''))
            for match in matches:
                # Normalisiere PAN (entferne Leerzeichen, F-Padding)
                pan = re.sub(r'[^0-9]', '', match).rstrip('F')
                
                if 13 <= len(pan) <= 19 and pan.startswith(('4', '5', '6')):
                    logger.debug(f"🎯 PAN aus PSE-Daten extrahiert: {pan[:6]}...{pan[-4:]}")
                    return pan
        
        return None
        
    except Exception as e:
        logger.debug(f"PSE-PAN-Extraktion fehlgeschlagen: {e}")
        return None

def enhanced_visa_recognition(pan: str, raw_data: str, card_type: str) -> Dict[str, Any]:
    """
    Erweiterte Visa-Kartenerkennung für neue problematische Karten.
    """
    result = {
        'enhanced': False,
        'original_pan': pan,
        'original_type': card_type,
        'new_pan': pan,
        'new_type': card_type,
        'confidence': 0,
        'analysis': {},
        'auto_approve': False,
        'reasons': [],
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # PSE-Analyse
        pse_analysis = analyze_pse_response(raw_data)
        result['analysis']['pse'] = pse_analysis
        result['confidence'] += pse_analysis['confidence']
        
        # AID-Fehler-Analyse
        aid_analysis = analyze_aid_failures(raw_data)
        result['analysis']['aid_failures'] = aid_analysis
        result['confidence'] += aid_analysis['confidence_boost']
        
        # PAN-Extraktion falls nicht vorhanden
        if not pan:
            extracted_pan = extract_pan_from_pse_data(raw_data)
            if extracted_pan:
                result['new_pan'] = extracted_pan
                result['confidence'] += 25
                result['reasons'].append(f'PAN aus PSE extrahiert: {extracted_pan[:6]}...{extracted_pan[-4:]}')
                pan = extracted_pan
        
        # Spezielle Visa-Behandlung
        if pan and pan.startswith('4'):
            pan_prefix = pan[:6]
            
            if pan_prefix in ENHANCED_VISA_PATTERNS:
                pattern_info = ENHANCED_VISA_PATTERNS[pan_prefix]
                
                # Prüfe spezielle Bedingungen
                conditions_met = True
                
                # PSE-Erfolg erforderlich?
                if pattern_info.get('pse_required') and not pse_analysis['pse_success']:
                    conditions_met = False
                    result['reasons'].append('PSE-Erfolg erforderlich, aber nicht gefunden')
                
                # Erwartete AID-Fehler?
                if pattern_info.get('aid_failures_expected'):
                    expected_aids = pattern_info['aid_failures_expected']
                    failed_aids = aid_analysis['aid_failures']
                    
                    if any(aid in failed_aids for aid in expected_aids):
                        result['confidence'] += pattern_info.get('confidence_boost', 0)
                        result['reasons'].append('Erwartete AID-Fehler bestätigen Kartentyp')
                
                if conditions_met:
                    result['enhanced'] = True
                    result['new_type'] = pattern_info['type']
                    result['auto_approve'] = pattern_info.get('auto_approve', False)
                    result['confidence'] += pattern_info.get('confidence_boost', 0)
                    result['reasons'].append(f'Erkannt als {pattern_info["name"]}')
                    
                    logger.info(f"🎯 Enhanced Visa Recognition: {pattern_info['name']} (Konfidenz: {result['confidence']}%)")
        
        # Fallback für unbekannte Visa-Karten mit PSE-Erfolg
        elif pan and pan.startswith('4') and pse_analysis['pse_success']:
            result['enhanced'] = True
            result['new_type'] = 'visa_pse_success'
            result['confidence'] += 30
            result['reasons'].append('Visa-Karte mit PSE-Erfolg')
            
            # Auto-Approve bei hoher Konfidenz
            if result['confidence'] >= 60:
                result['auto_approve'] = True
                result['reasons'].append('Auto-Genehmigung bei hoher Konfidenz')
        
        # Finale Bewertung
        if result['confidence'] >= 70:
            result['status'] = 'high_confidence'
        elif result['confidence'] >= 40:
            result['status'] = 'medium_confidence'
        else:
            result['status'] = 'low_confidence'
        
        return result
        
    except Exception as e:
        logger.error(f"Enhanced Visa Recognition fehlgeschlagen: {e}")
        result['error'] = str(e)
        return result

def create_learning_data(recognition_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erstellt Lerndaten für kontinuierliche Verbesserung.
    """
    learning_data = {
        'timestamp': datetime.now().isoformat(),
        'pan_prefix': recognition_result.get('new_pan', '')[:6] if recognition_result.get('new_pan') else None,
        'recognition_success': recognition_result.get('enhanced', False),
        'confidence': recognition_result.get('confidence', 0),
        'pse_success': recognition_result.get('analysis', {}).get('pse', {}).get('pse_success', False),
        'aid_failures': recognition_result.get('analysis', {}).get('aid_failures', {}).get('aid_failures', []),
        'auto_approved': recognition_result.get('auto_approve', False),
        'card_type': recognition_result.get('new_type')
    }
    
    return learning_data

# Test-Funktionen
if __name__ == "__main__":
    print("🧪 Enhanced Card Recognition Tests")
    print("=" * 60)
    
    # Test mit neuen problematischen Visa-Logs
    test_data = """
    german_contactless_pse    OK
    9000    
    00 A4 04 00 0E 32 50 41 59 2E ...
    6F 67 84 0E 32 50 41 59 2E 53 ...
    select_german_aid_A0000001523010    Fehler
    6A82    
    00 A4 04 00 07 A0 00 00 01 52 ...
    Keine Response
    PAN: 4220560000002044
    """
    
    result = enhanced_visa_recognition('4220560000002044', test_data, 'unknown_card')
    
    print(f"Enhanced: {'✅' if result['enhanced'] else '❌'}")
    print(f"New Type: {result['new_type']}")
    print(f"Confidence: {result['confidence']}%")
    print(f"Auto-Approve: {'✅' if result['auto_approve'] else '❌'}")
    print(f"Status: {result.get('status')}")
    
    if result['reasons']:
        print("Reasons:")
        for reason in result['reasons']:
            print(f"  • {reason}")
    
    print("\n✅ Test completed")