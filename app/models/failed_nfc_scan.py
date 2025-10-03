import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from ..config import DATA_DIR
from ..logger import log_system, log_error

class FailedNFCScanManager:
    """
    Verwaltet die Speicherung und Analyse von fehlgeschlagenen NFC-Scan-Rohdaten.
    
    Diese Klasse speichert alle APDU-Responses, Befehle und Metadaten von NFC-Karten,
    die nicht erfolgreich gescannt werden konnten, um später die nfc_reader.py 
    Funktionalität zu verbessern.
    """
    
    def __init__(self):
        """Initialisiere den FailedNFCScanManager und erstelle die Datenbank."""
        self.db_path = os.path.join(DATA_DIR, "failed_nfc_scans.db")
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialisiert die SQLite-Datenbank mit den benötigten Tabellen."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS failed_scans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        card_type TEXT,
                        attempted_aids TEXT,  -- JSON array of attempted AIDs
                        total_commands INTEGER DEFAULT 0,
                        successful_commands INTEGER DEFAULT 0,
                        error_summary TEXT,   -- JSON object with error counts
                        raw_atr_data TEXT,    -- Raw ATR (Answer to Reset) data
                        uid_data TEXT,        -- Card UID if available
                        analysis_notes TEXT,  -- For manual notes
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS apdu_responses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scan_id INTEGER NOT NULL,
                        command_sequence INTEGER NOT NULL,
                        command_name TEXT NOT NULL,
                        command_apdu TEXT NOT NULL,   -- Hex string of APDU command
                        response_apdu TEXT,           -- Hex string of APDU response
                        sw1 TEXT NOT NULL,            -- Status Word 1
                        sw2 TEXT NOT NULL,            -- Status Word 2
                        success BOOLEAN NOT NULL,
                        error_message TEXT,
                        execution_time_ms REAL,      -- Command execution time
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (scan_id) REFERENCES failed_scans (id)
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS card_analysis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scan_id INTEGER NOT NULL,
                        analysis_type TEXT NOT NULL,  -- 'pattern', 'emv_tag', 'bcd_decode', etc.
                        analysis_result TEXT,         -- JSON with analysis results
                        confidence_score REAL,       -- 0.0 to 1.0
                        recommendation TEXT,          -- What to improve
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (scan_id) REFERENCES failed_scans (id)
                    )
                """)
                
                # Indices für bessere Performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_scans_timestamp ON failed_scans (timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_scans_card_type ON failed_scans (card_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_apdu_responses_scan_id ON apdu_responses (scan_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_apdu_responses_success ON apdu_responses (success)")
                
                conn.commit()
                log_system("Failed NFC Scans Datenbank erfolgreich initialisiert")
                
        except Exception as e:
            log_error(f"Fehler beim Initialisieren der Failed NFC Scans Datenbank: {e}")
            raise
    
    def save_failed_scan(self,
                        card_type: str,
                        apdu_responses: List[Dict[str, Any]],
                        atr_data: Optional[str] = None,
                        uid_data: Optional[str] = None,
                        analysis_notes: Optional[str] = None) -> Optional[int]:
        """
        Speichert einen fehlgeschlagenen NFC-Scan mit allen Rohdaten.
        
        Args:
            card_type: Erkannter oder vermuteter Kartentyp
            apdu_responses: Liste der APDU-Befehle und -Antworten
            atr_data: Raw ATR-Daten (hex string)
            uid_data: Karten-UID falls verfügbar
            analysis_notes: Zusätzliche Analysehilfen
            
        Returns:
            Die ID des gespeicherten Scans oder None bei Fehler
        """
        try:
            # Extrahiere Metadaten aus den APDU-Responses
            attempted_aids = []
            total_commands = len(apdu_responses)
            successful_commands = 0
            error_counts = {}
            
            for response in apdu_responses:
                # Sammle AIDs aus Select-Commands
                command_name = response.get("command", "")
                if "aid" in command_name.lower() or "select" in command_name.lower():
                    apdu = response.get("apdu", "")
                    if apdu and len(apdu) > 10:  # Mindestlänge für AID-Selektion
                        attempted_aids.append(apdu)
                
                # Zähle erfolgreiche Commands
                if response.get("success", False):
                    successful_commands += 1
                
                # Sammle Fehlercodes
                sw1 = response.get("sw1", "")
                sw2 = response.get("sw2", "")
                if sw1 and sw2 and (sw1 != "90" or sw2 != "00"):
                    error_code = f"{sw1}{sw2}"
                    error_counts[error_code] = error_counts.get(error_code, 0) + 1
            
            timestamp = datetime.now().isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                # Speichere Haupt-Scan-Record
                cursor = conn.execute("""
                    INSERT INTO failed_scans 
                    (timestamp, card_type, attempted_aids, total_commands, 
                     successful_commands, error_summary, raw_atr_data, uid_data, analysis_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    card_type,
                    json.dumps(list(set(attempted_aids))),  # Unique AIDs
                    total_commands,
                    successful_commands,
                    json.dumps(error_counts),
                    atr_data,
                    uid_data,
                    analysis_notes
                ))
                
                scan_id = cursor.lastrowid
                
                # Speichere einzelne APDU-Responses
                for sequence, response in enumerate(apdu_responses):
                    conn.execute("""
                        INSERT INTO apdu_responses 
                        (scan_id, command_sequence, command_name, command_apdu, 
                         response_apdu, sw1, sw2, success, error_message, execution_time_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        scan_id,
                        sequence,
                        response.get("command", "unknown"),
                        response.get("apdu", ""),
                        response.get("response", ""),
                        response.get("sw1", ""),
                        response.get("sw2", ""),
                        response.get("success", False),
                        response.get("note", ""),
                        response.get("execution_time", None)
                    ))
                
                conn.commit()
                
                log_system(f"Fehlgeschlagener NFC-Scan gespeichert: ID={scan_id}, Typ={card_type}, Commands={total_commands}, Erfolg={successful_commands}")
                return scan_id
                
        except Exception as e:
            log_error(f"Fehler beim Speichern des fehlgeschlagenen NFC-Scans: {e}")
            return None
    
    def add_analysis_result(self,
                           scan_id: int,
                           analysis_type: str,
                           result: Dict[str, Any],
                           confidence: float,
                           recommendation: str) -> bool:
        """
        Fügt ein Analyseergebnis zu einem gespeicherten Scan hinzu.
        
        Args:
            scan_id: ID des Scans
            analysis_type: Art der Analyse (z.B. 'pattern_matching', 'emv_parsing')
            result: Analyseergebnis als Dictionary
            confidence: Vertrauenswert (0.0 bis 1.0)
            recommendation: Empfehlung zur Verbesserung
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO card_analysis 
                    (scan_id, analysis_type, analysis_result, confidence_score, recommendation)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    scan_id,
                    analysis_type,
                    json.dumps(result),
                    confidence,
                    recommendation
                ))
                conn.commit()
                
            log_system(f"Analyseergebnis hinzugefügt: Scan ID={scan_id}, Typ={analysis_type}")
            return True
            
        except Exception as e:
            log_error(f"Fehler beim Hinzufügen des Analyseergebnisses: {e}")
            return False
    
    def get_failed_scans(self,
                        limit: int = 50,
                        card_type: Optional[str] = None,
                        min_success_rate: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Holt fehlgeschlagene Scans mit Filtermöglichkeiten.
        
        Args:
            limit: Maximale Anzahl der Ergebnisse
            card_type: Filter nach Kartentyp
            min_success_rate: Minimale Erfolgsrate (0.0 bis 1.0)
            
        Returns:
            Liste der fehlgeschlagenen Scans
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Für dict-ähnliche Zugriffe
                
                query = """
                    SELECT * FROM failed_scans 
                    WHERE 1=1
                """
                params = []
                
                if card_type:
                    query += " AND card_type = ?"
                    params.append(card_type)
                
                if min_success_rate is not None:
                    query += " AND (CAST(successful_commands AS FLOAT) / total_commands) >= ?"
                    params.append(min_success_rate)
                
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                scans = [dict(row) for row in cursor.fetchall()]
                
                # Lade auch die APDU-Responses für jeden Scan
                for scan in scans:
                    scan_id = scan['id']
                    cursor = conn.execute("""
                        SELECT * FROM apdu_responses 
                        WHERE scan_id = ? 
                        ORDER BY command_sequence
                    """, (scan_id,))
                    scan['apdu_responses'] = [dict(row) for row in cursor.fetchall()]
                
                return scans
                
        except Exception as e:
            log_error(f"Fehler beim Abrufen der fehlgeschlagenen Scans: {e}")
            return []
    
    def get_scan_statistics(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über fehlgeschlagene Scans zurück.
        
        Returns:
            Dictionary mit Statistiken
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Grundlegende Statistiken
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_failed_scans,
                        AVG(CAST(successful_commands AS FLOAT) / total_commands) as avg_success_rate,
                        COUNT(DISTINCT card_type) as unique_card_types,
                        MIN(created_at) as first_scan,
                        MAX(created_at) as last_scan
                    FROM failed_scans
                """)
                basic_stats = dict(cursor.fetchone()) if cursor.fetchone() else {}
                
                # Kartentyp-Verteilung
                cursor = conn.execute("""
                    SELECT card_type, COUNT(*) as count 
                    FROM failed_scans 
                    GROUP BY card_type 
                    ORDER BY count DESC
                """)
                card_type_distribution = [dict(row) for row in cursor.fetchall()]
                
                # Häufigste Fehlercodes
                cursor = conn.execute("""
                    SELECT sw1 || sw2 as error_code, COUNT(*) as count
                    FROM apdu_responses 
                    WHERE success = 0 AND sw1 != '' AND sw2 != ''
                    GROUP BY error_code 
                    ORDER BY count DESC 
                    LIMIT 10
                """)
                common_errors = [dict(row) for row in cursor.fetchall()]
                
                return {
                    "basic_statistics": basic_stats,
                    "card_type_distribution": card_type_distribution,
                    "common_error_codes": common_errors,
                    "database_path": self.db_path
                }
                
        except Exception as e:
            log_error(f"Fehler beim Abrufen der Scan-Statistiken: {e}")
            return {}
    
    def export_scan_data(self, scan_id: int, format: str = 'json') -> Optional[str]:
        """
        Exportiert einen spezifischen Scan für externe Analyse.
        
        Args:
            scan_id: ID des zu exportierenden Scans
            format: Export-Format ('json', 'csv')
            
        Returns:
            Exportierte Daten als String oder None bei Fehler
        """
        try:
            scans = self.get_failed_scans(limit=1)
            if not scans:
                return None
            
            scan = next((s for s in scans if s['id'] == scan_id), None)
            if not scan:
                return None
            
            if format.lower() == 'json':
                return json.dumps(scan, indent=2, default=str)
            elif format.lower() == 'csv':
                # Vereinfachter CSV-Export für APDU-Responses
                lines = ["command_sequence,command_name,command_apdu,response_apdu,sw1,sw2,success"]
                for resp in scan.get('apdu_responses', []):
                    lines.append(f"{resp['command_sequence']},{resp['command_name']},{resp['command_apdu']},{resp['response_apdu']},{resp['sw1']},{resp['sw2']},{resp['success']}")
                return "\n".join(lines)
            
            return None
            
        except Exception as e:
            log_error(f"Fehler beim Exportieren der Scan-Daten: {e}")
            return None

# Globale Instanz
failed_scan_manager = FailedNFCScanManager() 