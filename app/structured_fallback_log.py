"""
Structured Fallback Log Module
===============================
Strukturiertes Logging-System für ALLE nicht erkannten Kartentypen.
Bietet detaillierte Analyse und Lösungsvorschläge.
"""

import logging
import json
import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from app import error_logger
from app.universal_card_fix import (
    universal_card_recognition,
    extract_pan_from_raw_data,
    analyze_apdu_errors,
    create_learning_entry
)

logger = logging.getLogger(__name__)

# Erweiterte Fehlerklassifizierung für alle Kartentypen
ERROR_CLASSIFICATIONS = {
    'CARD_NOT_RECOGNIZED': {
        'priority': 'HIGH',
        'color': '#dc3545',  # Rot
        'icon': '❌',
        'description': 'Karte wurde nicht erkannt'
    },
    'PAN_EXTRACTION_FAILED': {
        'priority': 'HIGH',
        'color': '#dc3545',
        'icon': '🔍',
        'description': 'PAN konnte nicht extrahiert werden'
    },
    'LUHN_VALIDATION_FAILED': {
        'priority': 'MEDIUM',
        'color': '#ffc107',  # Gelb
        'icon': '⚠️',
        'description': 'Luhn-Prüfung fehlgeschlagen'
    },
    'EMV_COMMUNICATION_ERROR': {
        'priority': 'MEDIUM',
        'color': '#ffc107',
        'icon': '📡',
        'description': 'EMV-Kommunikationsfehler'
    },
    'TIMEOUT_ERROR': {
        'priority': 'LOW',
        'color': '#17a2b8',  # Blau
        'icon': '⏱️',
        'description': 'Zeitüberschreitung'
    },
    'PARTIAL_READ': {
        'priority': 'MEDIUM',
        'color': '#fd7e14',  # Orange
        'icon': '📊',
        'description': 'Unvollständige Daten'
    },
    'UNKNOWN_ERROR': {
        'priority': 'LOW',
        'color': '#6c757d',  # Grau
        'icon': '❓',
        'description': 'Unbekannter Fehler'
    }
}

def classify_card_error(raw_data: str, error_type: str, pan: str = None) -> Dict[str, Any]:
    """
    Klassifiziert Kartenfehler für alle Kartentypen.
    """
    # Nutze universelle Kartenerkennung
    recognition = universal_card_recognition(pan, raw_data, error_type)
    
    # Bestimme Fehlerklassifikation
    if not recognition.get('pan') and not pan:
        classification = 'PAN_EXTRACTION_FAILED'
    elif recognition.get('luhn_valid') is False:
        classification = 'LUHN_VALIDATION_FAILED'
    elif recognition.get('apdu_analysis', {}).get('has_errors'):
        classification = 'EMV_COMMUNICATION_ERROR'
    elif 'timeout' in error_type.lower():
        classification = 'TIMEOUT_ERROR'
    elif recognition.get('confidence', 0) < 50:
        classification = 'CARD_NOT_RECOGNIZED'
    elif recognition.get('pan') and not recognition.get('recognized'):
        classification = 'PARTIAL_READ'
    else:
        classification = 'UNKNOWN_ERROR'
    
    return {
        'classification': classification,
        'recognition_result': recognition,
        'error_info': ERROR_CLASSIFICATIONS[classification]
    }

def create_structured_fallback_log(raw_data: str, error_type: str, pan: str = None) -> Dict[str, Any]:
    """
    Erstellt einen strukturierten Fallback-Log-Eintrag für alle Kartentypen.
    """
    timestamp = datetime.now().isoformat()
    
    # Klassifiziere den Fehler
    error_analysis = classify_card_error(raw_data, error_type, pan)
    classification = error_analysis['classification']
    recognition = error_analysis['recognition_result']
    error_info = error_analysis['error_info']
    
    # Erstelle strukturierten Eintrag
    log_entry = {
        'timestamp': timestamp,
        'classification': classification,
        'priority': error_info['priority'],
        'display': {
            'icon': error_info['icon'],
            'color': error_info['color'],
            'description': error_info['description']
        },
        'card_data': {
            'pan': recognition.get('pan'),
            'pan_masked': mask_pan(recognition.get('pan')) if recognition.get('pan') else None,
            'card_type': recognition.get('card_info', {}).get('name', 'Unknown'),
            'card_type_code': recognition.get('card_info', {}).get('type', 'unknown'),
            'confidence': recognition.get('confidence', 0)
        },
        'technical_details': {
            'original_error': error_type,
            'extraction_methods': recognition.get('extraction_methods', []),
            'luhn_valid': recognition.get('luhn_valid'),
            'apdu_errors': recognition.get('apdu_analysis', {}).get('errors', [])
        },
        'suggestions': recognition.get('suggestions', []),
        'raw_data': {
            'preview': raw_data[:300] if raw_data else '',
            'full': raw_data,
            'length': len(raw_data) if raw_data else 0
        },
        'learning_entry': create_learning_entry(
            recognition.get('pan'),
            raw_data,
            recognition.get('recognized', False)
        )
    }
    
    # Füge kartenspezifische Details hinzu
    if recognition.get('card_info'):
        card_info = recognition['card_info']
        if card_info.get('auto_approve'):
            log_entry['auto_action'] = {
                'approved': True,
                'reason': recognition.get('override_reason', 'Auto-approved card type')
            }
    
    return log_entry

def mask_pan(pan: str) -> str:
    """
    Maskiert die PAN für sichere Anzeige.
    """
    if not pan or len(pan) < 10:
        return '****'
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"

def log_structured_fallback(raw_data: str, error_type: str, pan: str = None) -> bool:
    """
    Hauptfunktion zum strukturierten Logging von Kartenfehlern.
    """
    try:
        # Erstelle strukturierten Log-Eintrag
        log_entry = create_structured_fallback_log(raw_data, error_type, pan)
        
        # Log mit passendem Level
        if log_entry['priority'] == 'HIGH':
            logger.error(f"{log_entry['display']['icon']} {log_entry['display']['description']}: "
                        f"{log_entry['card_data']['card_type']} "
                        f"({log_entry['card_data']['pan_masked']})")
        elif log_entry['priority'] == 'MEDIUM':
            logger.warning(f"{log_entry['display']['icon']} {log_entry['display']['description']}: "
                          f"{log_entry['card_data']['card_type']}")
        else:
            logger.info(f"{log_entry['display']['icon']} {log_entry['display']['description']}")
        
        # Speichere in Datenbank
        json_data = json.dumps(log_entry, ensure_ascii=False, indent=2)
        success = error_logger.log_fallback(json_data, log_entry['classification'])
        
        # Bei kritischen Fehlern zusätzliche Benachrichtigung
        if log_entry['priority'] == 'HIGH' and log_entry['card_data']['confidence'] > 0:
            logger.critical(f"🚨 KRITISCH: {log_entry['card_data']['card_type']} "
                          f"nicht erkannt ({log_entry['card_data']['pan_masked']})")
        
        return success
        
    except Exception as e:
        logger.error(f"Fehler beim strukturierten Logging: {e}")
        # Fallback zum Standard-Logger
        return error_logger.log_fallback(raw_data, error_type)

def get_structured_fallback_logs(
    limit: int = 50,
    filter_classification: str = None,
    filter_card_type: str = None,
    filter_priority: str = None
) -> List[Dict[str, Any]]:
    """
    Holt strukturierte Fallback-Logs mit erweiterten Filtermöglichkeiten.
    """
    try:
        # Hole alle Logs
        raw_logs = error_logger.get_fallback_logs(limit=limit * 3)
        structured_logs = []
        
        for log in raw_logs:
            try:
                # Parse strukturierte Daten
                if log['raw_data'].startswith('{'):
                    entry = json.loads(log['raw_data'])
                    
                    # Anwende Filter
                    if filter_classification and entry.get('classification') != filter_classification:
                        continue
                    if filter_card_type and entry.get('card_data', {}).get('card_type_code') != filter_card_type:
                        continue
                    if filter_priority and entry.get('priority') != filter_priority:
                        continue
                    
                    structured_logs.append(entry)
                else:
                    # Konvertiere alte Logs
                    entry = create_structured_fallback_log(
                        log['raw_data'],
                        log['error_type']
                    )
                    entry['timestamp'] = log['timestamp']
                    
                    # Anwende Filter
                    if filter_classification and entry.get('classification') != filter_classification:
                        continue
                    if filter_priority and entry.get('priority') != filter_priority:
                        continue
                    
                    structured_logs.append(entry)
                
                if len(structured_logs) >= limit:
                    break
                    
            except Exception as e:
                logger.debug(f"Fehler beim Parsen eines Logs: {e}")
                continue
        
        return structured_logs
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen strukturierter Logs: {e}")
        return []

def get_card_error_statistics() -> Dict[str, Any]:
    """
    Generiert umfassende Statistiken über Kartenfehler.
    """
    try:
        logs = get_structured_fallback_logs(limit=1000)
        
        stats = {
            'total_errors': len(logs),
            'by_classification': {},
            'by_card_type': {},
            'by_priority': {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0},
            'recognition_rate': 0,
            'common_apdu_errors': {},
            'extraction_methods': {},
            'recent_trends': [],
            'improvement_suggestions': []
        }
        
        recognized_count = 0
        
        for log in logs:
            # Klassifikation
            classification = log.get('classification', 'UNKNOWN')
            stats['by_classification'][classification] = stats['by_classification'].get(classification, 0) + 1
            
            # Kartentyp
            card_type = log.get('card_data', {}).get('card_type', 'Unknown')
            stats['by_card_type'][card_type] = stats['by_card_type'].get(card_type, 0) + 1
            
            # Priorität
            priority = log.get('priority', 'LOW')
            stats['by_priority'][priority] += 1
            
            # Erkennungsrate
            if log.get('learning_entry', {}).get('success'):
                recognized_count += 1
            
            # APDU-Fehler
            for error in log.get('technical_details', {}).get('apdu_errors', []):
                error_code = error.get('code', 'unknown')
                stats['common_apdu_errors'][error_code] = stats['common_apdu_errors'].get(error_code, 0) + 1
            
            # Extraktionsmethoden
            for method in log.get('technical_details', {}).get('extraction_methods', []):
                stats['extraction_methods'][method] = stats['extraction_methods'].get(method, 0) + 1
        
        # Berechne Erkennungsrate
        if stats['total_errors'] > 0:
            stats['recognition_rate'] = (recognized_count / stats['total_errors']) * 100
        
        # Generiere Verbesserungsvorschläge
        if stats['by_classification'].get('PAN_EXTRACTION_FAILED', 0) > 5:
            stats['improvement_suggestions'].append(
                'Viele PAN-Extraktionsfehler - EMV-Parser erweitern'
            )
        
        if stats['by_classification'].get('LUHN_VALIDATION_FAILED', 0) > 10:
            stats['improvement_suggestions'].append(
                'Häufige Luhn-Fehler - Validierung überprüfen oder lockern'
            )
        
        if stats['recognition_rate'] < 70:
            stats['improvement_suggestions'].append(
                f'Niedrige Erkennungsrate ({stats["recognition_rate"]:.1f}%) - Kartenpräfix-Datenbank erweitern'
            )
        
        # Top 3 problematische Kartentypen
        sorted_card_types = sorted(stats['by_card_type'].items(), key=lambda x: x[1], reverse=True)
        stats['top_problematic_cards'] = sorted_card_types[:3]
        
        return stats
        
    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Statistiken: {e}")
        return {'error': str(e)}

def export_learning_data() -> str:
    """
    Exportiert Lerndaten für externe Analyse.
    """
    try:
        logs = get_structured_fallback_logs(limit=500)
        learning_data = []
        
        for log in logs:
            if 'learning_entry' in log:
                learning_data.append(log['learning_entry'])
        
        return json.dumps(learning_data, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Fehler beim Export der Lerndaten: {e}")
        return json.dumps({'error': str(e)})

# Test-Funktionen
if __name__ == "__main__":
    print("Structured Fallback Log Tests")
    print("=" * 60)
    
    test_cases = [
        {
            'raw_data': 'PAN: 4220560000002044, Error: 6A82',
            'error_type': 'unknown_card',
            'pan': None
        },
        {
            'raw_data': '5A 08 53 72 28 86 97 11 63 66',
            'error_type': 'read_error',
            'pan': '5372288697116366'
        },
        {
            'raw_data': 'Timeout reading card',
            'error_type': 'timeout',
            'pan': None
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        log_entry = create_structured_fallback_log(
            test['raw_data'],
            test['error_type'],
            test['pan']
        )
        
        print(f"  Classification: {log_entry['classification']} {log_entry['display']['icon']}")
        print(f"  Priority: {log_entry['priority']}")
        print(f"  Card: {log_entry['card_data']['card_type']}")
        print(f"  Confidence: {log_entry['card_data']['confidence']}%")
        
        if log_entry['suggestions']:
            print(f"  Suggestions:")
            for suggestion in log_entry['suggestions']:
                print(f"    - {suggestion}")