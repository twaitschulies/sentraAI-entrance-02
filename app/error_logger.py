"""
Fallback Error Logger für NFC-Scan Fehler
=========================================

Dieses Modul stellt ein robustes Logging-System für fehlgeschlagene oder ungültige 
NFC-Scans bereit. Es verwendet eine SQLite-Datenbank zur persistenten Speicherung.

Funktionen:
- log_fallback(raw_data, error_type): Protokolliert einen Fehler
- get_fallback_logs(limit=50): Holt die neuesten Fehlerprotokolle
- export_fallback_logs_csv(): Exportiert Logs als CSV-String
- init_database(): Initialisiert die Datenbank-Tabelle
"""

import sqlite3
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import csv
import io


# Datenbank-Pfad
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'fallback_log.sqlite')
DB_DIR = os.path.dirname(DB_PATH)

# Logger für dieses Modul
logger = logging.getLogger(__name__)


def extract_readable_info(raw_data: str, error_type: str) -> str:
    """
    Extrahiert lesbare Informationen aus Rohdaten für bessere Auswertung.
    
    Args:
        raw_data (str): Die Rohdaten
        error_type (str): Der Fehlertyp
    
    Returns:
        str: Lesbare Informationen oder leerer String
    """
    try:
        readable_parts = []
        
        # Versuche Kreditkarten-/EC-Kartennummer zu erkennen
        import re
        card_patterns = [
            (r'\b(?:\d{4}[\s-]?){3}\d{4}\b', 'Kartennummer'),
            (r'\b\d{16}\b', 'Kartennummer'),
            (r'PAN[:\s]*([0-9A-Za-z]+)', 'PAN'),
            (r'UID[:\s]*([0-9A-Fa-f]+)', 'UID'),
            (r'ATR[:\s]*([0-9A-Fa-f\s]+)', 'ATR'),
        ]
        
        for pattern, label in card_patterns:
            match = re.search(pattern, raw_data, re.IGNORECASE)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                # Maskiere sensible Daten
                if len(value) > 8:
                    masked = value[:4] + '*' * (len(value) - 8) + value[-4:]
                else:
                    masked = value
                readable_parts.append(f"{label}: {masked}")
        
        # Kartentyp erkennen
        card_types = ['VISA', 'Mastercard', 'Maestro', 'American Express', 'Girocard', 'EC-Karte', 'Debitkarte', 'Kreditkarte']
        for card_type in card_types:
            if card_type.lower() in raw_data.lower():
                readable_parts.append(f"Kartentyp: {card_type}")
                break
        
        # Fehlertyp-spezifische Informationen
        if 'timeout' in error_type.lower():
            readable_parts.append("Zeitüberschreitung beim Lesen")
        elif 'invalid' in error_type.lower():
            readable_parts.append("Ungültiges Format")
        elif 'connection' in error_type.lower():
            readable_parts.append("Verbindungsfehler")
        
        return ' | '.join(readable_parts) if readable_parts else ''
        
    except Exception as e:
        logger.debug(f"Fehler beim Extrahieren lesbarer Informationen: {e}")
        return ''


def init_database() -> bool:
    """
    Initialisiert die SQLite-Datenbank und erstellt die fallback_log Tabelle.
    
    Returns:
        bool: True wenn erfolgreich, False bei Fehler
    """
    try:
        # Stelle sicher, dass das data-Verzeichnis existiert
        os.makedirs(DB_DIR, exist_ok=True)
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Erstelle Tabelle falls sie nicht existiert
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fallback_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Index für bessere Performance bei Zeitstempel-Abfragen
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_fallback_timestamp 
                ON fallback_log(timestamp DESC)
            ''')
            
            conn.commit()
            logger.info("✅ Fallback-Log Datenbank erfolgreich initialisiert")
            return True
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Initialisieren der Fallback-Log Datenbank: {e}")
        return False


def log_fallback(raw_data: str, error_type: str) -> bool:
    """
    Protokolliert einen fehlgeschlagenen oder ungültigen NFC-Scan.
    
    Args:
        raw_data (str): Die Rohdaten des fehlgeschlagenen Scans
        error_type (str): Art des Fehlers (z.B. 'invalid_format', 'read_error', 'timeout')
    
    Returns:
        bool: True wenn erfolgreich geloggt, False bei Fehler
    """
    try:
        # Validierung der Parameter
        if not raw_data or not error_type:
            logger.warning("⚠️ Leere raw_data oder error_type - Fallback-Log übersprungen")
            return False
        
        # Erweiterte Informationen extrahieren für bessere Lesbarkeit
        readable_info = extract_readable_info(raw_data, error_type)
        
        # Stelle sicher, dass die Datenbank existiert
        if not os.path.exists(DB_PATH):
            init_database()
        
        # ISO 8601 Zeitstempel
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Füge readable_info hinzu wenn verfügbar
            enhanced_raw_data = str(raw_data)
            if readable_info:
                enhanced_raw_data = f"{raw_data}\n[LESBARE INFO]: {readable_info}"
            
            cursor.execute('''
                INSERT INTO fallback_log (timestamp, raw_data, error_type)
                VALUES (?, ?, ?)
            ''', (timestamp, enhanced_raw_data, str(error_type)))
            
            conn.commit()
            
            # Log-ID für Referenz
            log_id = cursor.lastrowid
            info_msg = f"📝 Fallback-Log erstellt: ID={log_id}, Typ={error_type}"
            if readable_info:
                info_msg += f", Info: {readable_info[:100]}"
            logger.info(info_msg)
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Erstellen des Fallback-Logs: {e}")
        return False


def get_fallback_logs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Holt die neuesten Fallback-Logs aus der Datenbank.
    
    Args:
        limit (int): Maximale Anzahl der Ergebnisse (Standard: 50)
        offset (int): Anzahl der zu überspringenden Einträge (Standard: 0)
    
    Returns:
        List[Dict]: Liste der Fallback-Logs mit Feldern: id, timestamp, raw_data, error_type, created_at
    """
    try:
        if not os.path.exists(DB_PATH):
            logger.warning("⚠️ Fallback-Log Datenbank existiert nicht")
            return []
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row  # Für dict-ähnliche Zugriffe
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, timestamp, raw_data, error_type, created_at
                FROM fallback_log
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            logs = [dict(row) for row in cursor.fetchall()]
            
            logger.debug(f"📋 {len(logs)} Fallback-Logs abgerufen (limit={limit}, offset={offset})")
            return logs
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen der Fallback-Logs: {e}")
        return []


def get_fallback_log_count() -> int:
    """
    Zählt die Gesamtanzahl der Fallback-Logs.
    
    Returns:
        int: Anzahl der Logs in der Datenbank
    """
    try:
        if not os.path.exists(DB_PATH):
            return 0
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM fallback_log')
            count = cursor.fetchone()[0]
            
            return count
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Zählen der Fallback-Logs: {e}")
        return 0


def get_error_type_stats() -> Dict[str, int]:
    """
    Erstellt Statistiken über die verschiedenen Fehlertypen.
    
    Returns:
        Dict[str, int]: Dictionary mit error_type als Key und Anzahl als Value
    """
    try:
        if not os.path.exists(DB_PATH):
            return {}
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT error_type, COUNT(*) as count
                FROM fallback_log
                GROUP BY error_type
                ORDER BY count DESC
            ''')
            
            stats = {row[0]: row[1] for row in cursor.fetchall()}
            return stats
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Erstellen der Fehlertyp-Statistiken: {e}")
        return {}


def export_fallback_logs_csv(limit: Optional[int] = None) -> str:
    """
    Exportiert Fallback-Logs als CSV-String.
    
    Args:
        limit (Optional[int]): Begrenzt die Anzahl der exportierten Logs
    
    Returns:
        str: CSV-formatierte Logs
    """
    try:
        logs = get_fallback_logs(limit=limit or 1000)  # Standard: max 1000 Einträge
        
        if not logs:
            return "id,timestamp,raw_data,error_type,created_at\n"
        
        # CSV in String-Buffer erstellen
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['id', 'timestamp', 'raw_data', 'error_type', 'created_at'])
        
        writer.writeheader()
        for log in logs:
            writer.writerow(log)
        
        csv_content = output.getvalue()
        output.close()
        
        logger.info(f"📁 {len(logs)} Fallback-Logs als CSV exportiert")
        return csv_content
        
    except Exception as e:
        logger.error(f"❌ Fehler beim CSV-Export der Fallback-Logs: {e}")
        return "Fehler beim Export\n"


def cleanup_old_logs(days_to_keep: int = 90) -> int:
    """
    Löscht alte Fallback-Logs (Standard: älter als 90 Tage).
    
    Args:
        days_to_keep (int): Anzahl der Tage, die behalten werden sollen
    
    Returns:
        int: Anzahl der gelöschten Logs
    """
    try:
        if not os.path.exists(DB_PATH):
            return 0
        
        cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date.replace(days=-days_to_keep)
        cutoff_timestamp = cutoff_date.isoformat()
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Zähle zuerst, wie viele gelöscht werden
            cursor.execute('SELECT COUNT(*) FROM fallback_log WHERE timestamp < ?', (cutoff_timestamp,))
            count_to_delete = cursor.fetchone()[0]
            
            # Lösche alte Einträge
            cursor.execute('DELETE FROM fallback_log WHERE timestamp < ?', (cutoff_timestamp,))
            conn.commit()
            
            if count_to_delete > 0:
                logger.info(f"🧹 {count_to_delete} alte Fallback-Logs gelöscht (älter als {days_to_keep} Tage)")
            
            return count_to_delete
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Bereinigen alter Fallback-Logs: {e}")
        return 0


# Initialisiere Datenbank beim Import
if __name__ != "__main__":
    init_database()


# Test-Funktionen (nur wenn direkt ausgeführt)
if __name__ == "__main__":
    print("🧪 Teste Fallback Error Logger...")
    
    # Initialisiere DB
    success = init_database()
    print(f"Datenbank-Initialisierung: {'✅' if success else '❌'}")
    
    # Test-Log erstellen
    test_success = log_fallback("test_raw_data_12345", "test_error")
    print(f"Test-Log erstellt: {'✅' if test_success else '❌'}")
    
    # Logs abrufen
    logs = get_fallback_logs(limit=5)
    print(f"Logs abgerufen: {len(logs)} Einträge")
    
    for log in logs:
        print(f"  - {log['timestamp']}: {log['error_type']} | {log['raw_data'][:30]}...")
    
    # Statistiken
    stats = get_error_type_stats()
    print(f"Fehlertyp-Statistiken: {stats}")
    
    print("✅ Test abgeschlossen") 