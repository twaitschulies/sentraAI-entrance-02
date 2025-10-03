"""
Enhanced NFC Raw Data Analyzer
============================

Dieses Modul stellt ein erweitertes System zur Analyse und Extraktion von 
NFC-Karten-Rohdaten bereit, um zukünftige Kartenfreigaben zu ermöglichen.

Features:
- Strukturierte Rohdatenerfassung
- Intelligente Kartentyp-Erkennung  
- Extraktion relevanter Karten-Identifikatoren
- Auswertungshilfen für Admin-Entscheidungen
- Export-Funktionalitäten
"""

import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
import hashlib
import re
from ..config import DATA_DIR
from ..logger import log_system, log_error

logger = logging.getLogger(__name__)

@dataclass
class NFCCardIdentifier:
    """Strukturierte Repräsentation einer NFC-Karten-Identifikation."""
    card_hash: str          # SHA-256 Hash der Karte (für Privatsphäre)
    card_type: str          # Erkannter Kartentyp (z.B. "sparkasse", "volksbank") 
    partial_pan: str        # Teilweise PAN (erste 6 + letzte 4 Ziffern)
    uid_data: Optional[str] # UID falls verfügbar
    bank_identifier: Optional[str]  # BIN (Bank Identification Number)
    confidence_score: float # Vertrauensgrad der Erkennung (0.0-1.0)
    raw_data_size: int     # Größe der Rohdaten in Bytes
    scan_timestamp: str    # Zeitstempel des ersten Scans
    scan_count: int        # Anzahl der Scans dieser Karte

@dataclass
class APDUCommand:
    """Strukturierte APDU-Kommando-Daten."""
    command_name: str
    apdu_hex: str
    response_hex: str
    status_word: str
    success: bool
    execution_time_ms: float
    error_message: Optional[str] = None

class NFCRawDataAnalyzer:
    """
    Erweiterter Analyzer für NFC-Rohdaten mit Fokus auf Kartenfreigabe-Entscheidungen.
    """
    
    def __init__(self):
        self.db_path = os.path.join(DATA_DIR, "nfc_raw_data_analysis.db")
        self._init_database()
        
        # Bekannte Bank-BINs für bessere Kartentyp-Erkennung
        self.bank_bins = {
            # Deutsche Sparkassen
            "403570": "Sparkasse Dortmund",
            "520420": "Sparkasse Köln/Bonn", 
            "543330": "Sparkasse Münsterland Ost",
            "545230": "Kreissparkasse Düsseldorf",
            "547620": "Sparkasse Vest",
            "403570": "Sparkasse Dortmund",
            
            # Volksbanken/Raiffeisenbanken
            "471635": "Volksbank eG",
            "472135": "Raiffeisenbank eG",
            "402135": "Volksbank Raiffeisenbank eG",
            
            # Großbanken
            "444999": "Deutsche Bank",
            "454617": "Commerzbank", 
            "520030": "Postbank",
            "444999": "Deutsche Bank AG",
        }

    def _init_database(self) -> None:
        """Initialisiert die erweiterte SQLite-Datenbank."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                # Haupttabelle für NFC-Karten-Identifikatoren
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS nfc_card_identifiers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_hash TEXT UNIQUE NOT NULL,
                        card_type TEXT NOT NULL,
                        partial_pan TEXT,
                        uid_data TEXT,
                        bank_identifier TEXT,
                        confidence_score REAL DEFAULT 0.0,
                        raw_data_size INTEGER DEFAULT 0,
                        scan_timestamp TEXT NOT NULL,
                        scan_count INTEGER DEFAULT 1,
                        last_seen TEXT NOT NULL,
                        status TEXT DEFAULT 'unknown', -- unknown, approved, rejected
                        admin_notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Tabelle für detaillierte APDU-Kommandos
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS nfc_apdu_commands (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_id INTEGER NOT NULL,
                        scan_session_id TEXT NOT NULL,
                        command_sequence INTEGER NOT NULL,
                        command_name TEXT NOT NULL,
                        apdu_hex TEXT NOT NULL,
                        response_hex TEXT,
                        status_word TEXT NOT NULL,
                        success BOOLEAN NOT NULL,
                        execution_time_ms REAL,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (card_id) REFERENCES nfc_card_identifiers (id)
                    )
                """)
                
                # Tabelle für Rohdaten-Extrakte
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS nfc_raw_extracts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_id INTEGER NOT NULL,
                        extract_type TEXT NOT NULL, -- atr, uid, emv_response, etc.
                        raw_hex_data TEXT NOT NULL,
                        decoded_data TEXT,
                        extraction_method TEXT,
                        quality_score REAL DEFAULT 0.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (card_id) REFERENCES nfc_card_identifiers (id)
                    )
                """)
                
                # Index für bessere Performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_card_hash ON nfc_card_identifiers(card_hash)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_card_type ON nfc_card_identifiers(card_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON nfc_card_identifiers(status)")
                
            log_system("NFC Raw Data Analyzer Datenbank erfolgreich initialisiert")
            
        except Exception as e:
            log_error(f"Fehler bei der Initialisierung der NFC Raw Data Analyzer Datenbank: {e}")
            raise

    def analyze_and_store_nfc_scan(self, 
                                   card_type: str,
                                   apdu_responses: List[Dict],
                                   atr_data: Optional[str] = None,
                                   uid_data: Optional[str] = None,
                                   analysis_notes: Optional[str] = None) -> Optional[str]:
        """
        Analysiert und speichert einen NFC-Scan mit erweiterten Metadaten.
        
        Args:
            card_type: Erkannter Kartentyp
            apdu_responses: Liste der APDU-Kommandos und Responses
            atr_data: ATR-Daten als Hex-String
            uid_data: Karten-UID falls verfügbar
            analysis_notes: Zusätzliche Analyse-Notizen
            
        Returns:
            str: Session-ID des gespeicherten Scans oder None bei Fehler
        """
        try:
            # Generiere eine eindeutige Session-ID
            session_id = f"nfc_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(apdu_responses).encode()).hexdigest()[:8]}"
            
            # Extrahiere Karten-Identifikator
            card_identifier = self._extract_card_identifier(card_type, apdu_responses, atr_data, uid_data)
            
            if not card_identifier:
                log_error(f"Konnte keinen Karten-Identifikator aus Scan extrahieren: {session_id}")
                return None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Prüfe, ob diese Karte bereits bekannt ist
                cursor.execute("""
                    SELECT id, scan_count FROM nfc_card_identifiers 
                    WHERE card_hash = ?
                """, (card_identifier.card_hash,))
                
                existing_card = cursor.fetchone()
                
                if existing_card:
                    # Update existierende Karte
                    card_id, current_scan_count = existing_card
                    new_scan_count = current_scan_count + 1
                    
                    cursor.execute("""
                        UPDATE nfc_card_identifiers 
                        SET scan_count = ?, last_seen = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (new_scan_count, datetime.now().isoformat(), card_id))
                    
                    log_system(f"Bekannte NFC-Karte aktualisiert: {card_identifier.card_hash[:12]}... (Scan #{new_scan_count})")
                    
                else:
                    # Neue Karte hinzufügen
                    cursor.execute("""
                        INSERT INTO nfc_card_identifiers 
                        (card_hash, card_type, partial_pan, uid_data, bank_identifier, 
                         confidence_score, raw_data_size, scan_timestamp, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        card_identifier.card_hash,
                        card_identifier.card_type,
                        card_identifier.partial_pan,
                        card_identifier.uid_data,
                        card_identifier.bank_identifier,
                        card_identifier.confidence_score,
                        card_identifier.raw_data_size,
                        card_identifier.scan_timestamp,
                        datetime.now().isoformat()
                    ))
                    
                    card_id = cursor.lastrowid
                    log_system(f"Neue NFC-Karte registriert: {card_identifier.card_hash[:12]}... (ID: {card_id})")
                
                # Speichere APDU-Kommandos
                for i, response in enumerate(apdu_responses):
                    cursor.execute("""
                        INSERT INTO nfc_apdu_commands
                        (card_id, scan_session_id, command_sequence, command_name,
                         apdu_hex, response_hex, status_word, success, execution_time_ms, error_message)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        card_id,
                        session_id,
                        i + 1,
                        response.get('command', 'unknown'),
                        response.get('apdu', ''),
                        response.get('response', ''),
                        f"{response.get('sw1', '')}{ response.get('sw2', '')}",
                        response.get('success', False),
                        response.get('execution_time_ms'),
                        response.get('error_message')
                    ))
                
                # Speichere Rohdaten-Extrakte
                if atr_data:
                    cursor.execute("""
                        INSERT INTO nfc_raw_extracts
                        (card_id, extract_type, raw_hex_data, extraction_method, quality_score)
                        VALUES (?, ?, ?, ?, ?)
                    """, (card_id, 'atr', atr_data, 'direct_extraction', 1.0))
                
                if uid_data:
                    cursor.execute("""
                        INSERT INTO nfc_raw_extracts
                        (card_id, extract_type, raw_hex_data, extraction_method, quality_score)
                        VALUES (?, ?, ?, ?, ?)
                    """, (card_id, 'uid', uid_data, 'direct_extraction', 1.0))
                
                conn.commit()
                
            log_system(f"NFC-Scan erfolgreich analysiert und gespeichert: {session_id}")
            return session_id
            
        except Exception as e:
            log_error(f"Fehler beim Analysieren und Speichern des NFC-Scans: {e}")
            return None

    def _extract_card_identifier(self, 
                                 card_type: str,
                                 apdu_responses: List[Dict],
                                 atr_data: Optional[str],
                                 uid_data: Optional[str]) -> Optional[NFCCardIdentifier]:
        """
        Extrahiert einen eindeutigen aber privacy-sicheren Karten-Identifikator.
        """
        try:
            # Sammle alle verfügbaren Daten für Hash-Generierung
            hash_components = []
            
            if atr_data:
                hash_components.append(f"atr:{atr_data}")
            
            if uid_data:
                hash_components.append(f"uid:{uid_data}")
            
            # Sammle Response-Daten aus APDU-Kommandos
            successful_responses = []
            for response in apdu_responses:
                if response.get('success') and response.get('response'):
                    successful_responses.append(response.get('response', ''))
                    hash_components.append(f"resp:{response.get('response', '')}")
            
            if not hash_components:
                return None
            
            # Generiere Privacy-sicheren Hash
            hash_data = "|".join(sorted(hash_components))
            card_hash = hashlib.sha256(hash_data.encode()).hexdigest()
            
            # Versuche PAN-Extraktion für Teilanzeige
            partial_pan = self._extract_partial_pan(successful_responses)
            
            # Bestimme Bank-Identifikator
            bank_identifier = self._determine_bank_identifier(partial_pan, card_type)
            
            # Berechne Confidence Score
            confidence_score = self._calculate_confidence_score(apdu_responses, atr_data, uid_data)
            
            # Berechne Rohdaten-Größe
            raw_data_size = len(hash_data.encode())
            
            return NFCCardIdentifier(
                card_hash=card_hash,
                card_type=card_type,
                partial_pan=partial_pan,
                uid_data=uid_data,
                bank_identifier=bank_identifier,
                confidence_score=confidence_score,
                raw_data_size=raw_data_size,
                scan_timestamp=datetime.now().isoformat(),
                scan_count=1
            )
            
        except Exception as e:
            log_error(f"Fehler bei der Karten-Identifikator-Extraktion: {e}")
            return None

    def _extract_partial_pan(self, response_data: List[str]) -> Optional[str]:
        """
        Extrahiert eine Teilweise PAN (erste 6 + letzte 4 Ziffern) für Anzeigezwecke.
        """
        try:
            for response in response_data:
                # Suche nach PAN-ähnlichen Patterns in den Responses
                pan_patterns = [
                    r'([4-6]\d{15})',  # 16-stellige Kreditkarten-PAN
                    r'([4-6]\d{12,18})',  # Variable Länge
                ]
                
                for pattern in pan_patterns:
                    matches = re.findall(pattern, response.replace(' ', ''))
                    for match in matches:
                        if len(match) >= 13 and match.isdigit():
                            # Rückgabe: erste 6 + letzte 4 Ziffern
                            return f"{match[:6]}...{match[-4:]}"
                            
        except Exception as e:
            logger.debug(f"PAN-Extraktion fehlgeschlagen: {e}")
        
        return None

    def _determine_bank_identifier(self, partial_pan: Optional[str], card_type: str) -> Optional[str]:
        """
        Bestimmt den Bank-Identifikator basierend auf BIN und Kartentyp.
        """
        try:
            if partial_pan and len(partial_pan) >= 6:
                bin_code = partial_pan[:6]
                if bin_code in self.bank_bins:
                    return self.bank_bins[bin_code]
            
            # Fallback basierend auf Kartentyp
            type_mapping = {
                'sparkasse': 'Sparkassen-Finanzgruppe',
                'volksbank': 'Volksbanken Raiffeisenbanken',
                'deutsche_bank': 'Deutsche Bank AG',
                'commerzbank': 'Commerzbank AG',
                'postbank': 'Deutsche Postbank AG'
            }
            
            for key, value in type_mapping.items():
                if key in card_type.lower():
                    return value
                    
        except Exception as e:
            logger.debug(f"Bank-Identifikator-Bestimmung fehlgeschlagen: {e}")
        
        return None

    def _calculate_confidence_score(self, 
                                   apdu_responses: List[Dict],
                                   atr_data: Optional[str],
                                   uid_data: Optional[str]) -> float:
        """
        Berechnet einen Confidence Score für die Kartenidentifikation.
        """
        try:
            score = 0.0
            max_score = 0.0
            
            # ATR-Daten verfügbar (+0.3)
            max_score += 0.3
            if atr_data and len(atr_data) > 10:
                score += 0.3
            
            # UID-Daten verfügbar (+0.2)
            max_score += 0.2
            if uid_data and len(uid_data) > 6:
                score += 0.2
            
            # Erfolgreiche APDU-Kommandos (+0.5)
            max_score += 0.5
            if apdu_responses:
                successful_commands = sum(1 for r in apdu_responses if r.get('success'))
                total_commands = len(apdu_responses)
                
                if total_commands > 0:
                    success_ratio = successful_commands / total_commands
                    score += 0.5 * success_ratio
            
            return min(score / max_score, 1.0) if max_score > 0 else 0.0
            
        except Exception:
            return 0.0

    def get_unknown_cards(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Holt alle unbekannten Karten zur Admin-Bewertung.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, card_hash, card_type, partial_pan, bank_identifier,
                           confidence_score, scan_count, scan_timestamp, last_seen,
                           status, admin_notes
                    FROM nfc_card_identifiers 
                    WHERE status = 'unknown'
                    ORDER BY scan_count DESC, last_seen DESC
                    LIMIT ?
                """, (limit,))
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    card_data = dict(zip(columns, row))
                    results.append(card_data)
                
                return results
                
        except Exception as e:
            log_error(f"Fehler beim Laden unbekannter Karten: {e}")
            return []

    def get_all_cards(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Holt alle Karten (alle Status) für das vereinheitlichte Fallback-Log.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, card_hash, card_type, partial_pan, bank_identifier,
                           confidence_score, scan_count, scan_timestamp, last_seen,
                           status, admin_notes
                    FROM nfc_card_identifiers 
                    ORDER BY 
                        CASE status 
                            WHEN 'unknown' THEN 0 
                            WHEN 'approved' THEN 1 
                            WHEN 'rejected' THEN 2 
                            ELSE 3 
                        END,
                        scan_count DESC, 
                        last_seen DESC
                    LIMIT ?
                """, (limit,))
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    card_data = dict(zip(columns, row))
                    results.append(card_data)
                
                return results
                
        except Exception as e:
            log_error(f"Fehler beim Laden aller Karten: {e}")
            return []

    def update_card_status(self, card_id: int, status: str, admin_notes: Optional[str] = None) -> bool:
        """
        Aktualisiert den Status einer Karte (approved/rejected/unknown).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE nfc_card_identifiers 
                    SET status = ?, admin_notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, admin_notes, card_id))
                
                if cursor.rowcount > 0:
                    log_system(f"Kartenstatus aktualisiert: ID={card_id}, Status={status}")
                    return True
                else:
                    log_error(f"Karte nicht gefunden für Status-Update: ID={card_id}")
                    return False
                    
        except Exception as e:
            log_error(f"Fehler beim Aktualisieren des Kartenstatus: {e}")
            return False

    def get_card_details(self, card_id: int) -> Optional[Dict[str, Any]]:
        """
        Holt detaillierte Informationen zu einer Karte inklusive APDU-Kommandos.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Hole Karten-Grunddaten
                cursor.execute("""
                    SELECT * FROM nfc_card_identifiers WHERE id = ?
                """, (card_id,))
                
                card_row = cursor.fetchone()
                if not card_row:
                    return None
                
                columns = [desc[0] for desc in cursor.description]
                card_data = dict(zip(columns, card_row))
                
                # Hole APDU-Kommandos
                cursor.execute("""
                    SELECT command_name, apdu_hex, response_hex, status_word, success,
                           execution_time_ms, error_message
                    FROM nfc_apdu_commands 
                    WHERE card_id = ?
                    ORDER BY command_sequence
                """, (card_id,))
                
                apdu_columns = [desc[0] for desc in cursor.description]
                apdu_commands = []
                
                for row in cursor.fetchall():
                    apdu_data = dict(zip(apdu_columns, row))
                    apdu_commands.append(apdu_data)
                
                card_data['apdu_commands'] = apdu_commands
                
                # Hole Rohdaten-Extrakte
                cursor.execute("""
                    SELECT extract_type, raw_hex_data, decoded_data, extraction_method, quality_score
                    FROM nfc_raw_extracts 
                    WHERE card_id = ?
                    ORDER BY created_at
                """, (card_id,))
                
                extract_columns = [desc[0] for desc in cursor.description]
                raw_extracts = []
                
                for row in cursor.fetchall():
                    extract_data = dict(zip(extract_columns, row))
                    raw_extracts.append(extract_data)
                
                card_data['raw_extracts'] = raw_extracts
                
                return card_data
                
        except Exception as e:
            log_error(f"Fehler beim Laden der Kartendetails: {e}")
            return None

    def export_card_data(self, status_filter: Optional[str] = None) -> str:
        """
        Exportiert Kartendaten als JSON für weitere Analyse.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT id, card_hash, card_type, partial_pan, bank_identifier,
                           confidence_score, scan_count, scan_timestamp, last_seen,
                           status, admin_notes
                    FROM nfc_card_identifiers
                """
                
                params = ()
                if status_filter:
                    query += " WHERE status = ?"
                    params = (status_filter,)
                
                query += " ORDER BY scan_count DESC, last_seen DESC"
                
                cursor.execute(query, params)
                
                columns = [desc[0] for desc in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    card_data = dict(zip(columns, row))
                    results.append(card_data)
                
                export_data = {
                    'export_timestamp': datetime.now().isoformat(),
                    'total_cards': len(results),
                    'status_filter': status_filter,
                    'cards': results
                }
                
                return json.dumps(export_data, indent=2, ensure_ascii=False)
                
        except Exception as e:
            log_error(f"Fehler beim Exportieren der Kartendaten: {e}")
            return json.dumps({'error': str(e)})


# Globale Instanz
nfc_raw_data_analyzer = NFCRawDataAnalyzer() 