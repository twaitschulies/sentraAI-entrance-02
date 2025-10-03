"""
Webhook Logger Module
=====================
Dediziertes Logging-System für alle Webhook-Anfragen.
Protokolliert wann, wie oft und mit welchen Daten Webhooks ausgelöst werden.
"""

import sqlite3
import os
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import csv
import io

logger = logging.getLogger(__name__)

# Datenbank-Pfad für Webhook-Logs
WEBHOOK_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'webhook_logs.sqlite')
WEBHOOK_DB_DIR = os.path.dirname(WEBHOOK_DB_PATH)

def init_webhook_database() -> bool:
    """
    Initialisiert die SQLite-Datenbank für Webhook-Logs.
    """
    try:
        # Stelle sicher, dass das data-Verzeichnis existiert
        os.makedirs(WEBHOOK_DB_DIR, exist_ok=True)
        
        with sqlite3.connect(WEBHOOK_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Erstelle Tabelle für Webhook-Logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS webhook_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    webhook_type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    method TEXT DEFAULT 'GET',
                    payload TEXT,
                    response_code INTEGER,
                    response_time_ms INTEGER,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    trigger_source TEXT,
                    card_pan_masked TEXT,
                    barcode_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Index für bessere Performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_webhook_timestamp 
                ON webhook_logs(timestamp DESC)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_webhook_type 
                ON webhook_logs(webhook_type)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_webhook_success 
                ON webhook_logs(success)
            ''')
            
            conn.commit()
            logger.info("✅ Webhook-Log Datenbank erfolgreich initialisiert")
            return True
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Initialisieren der Webhook-Log Datenbank: {e}")
        return False

def log_webhook_request(
    webhook_type: str,
    url: str,
    method: str = 'GET',
    payload: Dict[str, Any] = None,
    response_code: int = None,
    response_time_ms: int = None,
    success: bool = False,
    error_message: str = None,
    trigger_source: str = None,
    card_pan: str = None,
    barcode_data: str = None
) -> bool:
    """
    Protokolliert eine Webhook-Anfrage mit allen relevanten Details.
    """
    try:
        # Stelle sicher, dass die Datenbank existiert
        if not os.path.exists(WEBHOOK_DB_PATH):
            init_webhook_database()
        
        # Maskiere sensible Daten
        card_pan_masked = None
        if card_pan and len(card_pan) >= 10:
            card_pan_masked = f"{card_pan[:6]}{'*' * (len(card_pan) - 10)}{card_pan[-4:]}"
        elif card_pan:
            card_pan_masked = f"{card_pan[:2]}{'*' * (len(card_pan) - 2)}"
        
        # ISO 8601 Zeitstempel
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(WEBHOOK_DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO webhook_logs (
                    timestamp, webhook_type, url, method, payload, 
                    response_code, response_time_ms, success, error_message,
                    trigger_source, card_pan_masked, barcode_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                webhook_type,
                url,
                method,
                json.dumps(payload) if payload else None,
                response_code,
                response_time_ms,
                success,
                error_message,
                trigger_source,
                card_pan_masked,
                barcode_data
            ))
            
            conn.commit()
            log_id = cursor.lastrowid
            
            # Log-Ausgabe je nach Erfolg
            if success:
                logger.info(f"📡 Webhook erfolgreich: {webhook_type} -> {url} (ID: {log_id}, {response_time_ms}ms)")
            else:
                logger.warning(f"⚠️ Webhook fehlgeschlagen: {webhook_type} -> {url} (ID: {log_id}) - {error_message}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Webhook-Logging: {e}")
        return False

def get_webhook_logs(
    limit: int = 50,
    webhook_type: str = None,
    success_only: bool = None,
    hours_back: int = None
) -> List[Dict[str, Any]]:
    """
    Holt Webhook-Logs mit verschiedenen Filtermöglichkeiten.
    """
    try:
        if not os.path.exists(WEBHOOK_DB_PATH):
            logger.warning("⚠️ Webhook-Log Datenbank existiert nicht")
            return []
        
        with sqlite3.connect(WEBHOOK_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Baue Query dynamisch auf
            query = '''
                SELECT id, timestamp, webhook_type, url, method, payload,
                       response_code, response_time_ms, success, error_message,
                       trigger_source, card_pan_masked, barcode_data, created_at
                FROM webhook_logs
                WHERE 1=1
            '''
            params = []
            
            # Filter anwenden
            if webhook_type:
                query += ' AND webhook_type = ?'
                params.append(webhook_type)
            
            if success_only is not None:
                query += ' AND success = ?'
                params.append(success_only)
            
            if hours_back:
                cutoff = datetime.now() - timedelta(hours=hours_back)
                query += ' AND datetime(timestamp) >= datetime(?)'
                params.append(cutoff.isoformat())
            
            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            logs = [dict(row) for row in cursor.fetchall()]
            
            logger.debug(f"📋 {len(logs)} Webhook-Logs abgerufen")
            return logs
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen der Webhook-Logs: {e}")
        return []

def get_webhook_statistics(hours_back: int = 24) -> Dict[str, Any]:
    """
    Erstellt Statistiken über Webhook-Aufrufe.
    """
    try:
        if not os.path.exists(WEBHOOK_DB_PATH):
            return {'total': 0, 'error': 'No database'}
        
        cutoff = datetime.now() - timedelta(hours=hours_back)
        
        with sqlite3.connect(WEBHOOK_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Grundstatistiken
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    AVG(response_time_ms) as avg_response_time
                FROM webhook_logs 
                WHERE datetime(timestamp) >= datetime(?)
            ''', (cutoff.isoformat(),))
            
            result = cursor.fetchone()
            total, successful, avg_response_time = result
            
            stats = {
                'period_hours': hours_back,
                'total_requests': total or 0,
                'successful_requests': successful or 0,
                'failed_requests': (total or 0) - (successful or 0),
                'success_rate': round((successful / total * 100) if total > 0 else 0, 2),
                'avg_response_time_ms': round(avg_response_time or 0, 2),
                'by_type': {},
                'by_hour': {},
                'recent_errors': []
            }
            
            # Nach Webhook-Typ
            cursor.execute('''
                SELECT webhook_type, COUNT(*) as count,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful
                FROM webhook_logs 
                WHERE datetime(timestamp) >= datetime(?)
                GROUP BY webhook_type
                ORDER BY count DESC
            ''', (cutoff.isoformat(),))
            
            for row in cursor.fetchall():
                webhook_type, count, successful = row
                stats['by_type'][webhook_type] = {
                    'total': count,
                    'successful': successful,
                    'failed': count - successful,
                    'success_rate': round((successful / count * 100) if count > 0 else 0, 2)
                }
            
            # Stundenweise Verteilung (letzte 24h)
            cursor.execute('''
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM webhook_logs 
                WHERE datetime(timestamp) >= datetime(?)
                GROUP BY strftime('%H', timestamp)
                ORDER BY hour
            ''', (cutoff.isoformat(),))
            
            for row in cursor.fetchall():
                hour, count = row
                stats['by_hour'][f"{hour}:00"] = count
            
            # Aktuelle Fehler
            cursor.execute('''
                SELECT timestamp, webhook_type, url, error_message
                FROM webhook_logs 
                WHERE success = 0 AND datetime(timestamp) >= datetime(?)
                ORDER BY timestamp DESC
                LIMIT 5
            ''', (cutoff.isoformat(),))
            
            stats['recent_errors'] = [
                {
                    'timestamp': row[0],
                    'type': row[1],
                    'url': row[2],
                    'error': row[3]
                }
                for row in cursor.fetchall()
            ]
            
            return stats
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Erstellen der Webhook-Statistiken: {e}")
        return {'error': str(e)}

def export_webhook_logs_csv(hours_back: int = 24) -> str:
    """
    Exportiert Webhook-Logs als CSV.
    """
    try:
        logs = get_webhook_logs(limit=1000, hours_back=hours_back)
        
        if not logs:
            return "timestamp,webhook_type,url,method,success,response_code,response_time_ms,error_message\n"
        
        # CSV in String-Buffer erstellen
        output = io.StringIO()
        fieldnames = ['timestamp', 'webhook_type', 'url', 'method', 'success', 
                     'response_code', 'response_time_ms', 'error_message', 
                     'trigger_source', 'card_pan_masked', 'barcode_data']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        writer.writeheader()
        for log in logs:
            # Entferne payload für CSV (zu komplex)
            log_copy = dict(log)
            log_copy.pop('payload', None)
            log_copy.pop('id', None)
            log_copy.pop('created_at', None)
            writer.writerow(log_copy)
        
        csv_content = output.getvalue()
        output.close()
        
        logger.info(f"📁 {len(logs)} Webhook-Logs als CSV exportiert")
        return csv_content
        
    except Exception as e:
        logger.error(f"❌ Fehler beim CSV-Export der Webhook-Logs: {e}")
        return "Fehler beim Export\n"

def cleanup_old_webhook_logs(days_to_keep: int = 30) -> int:
    """
    Löscht alte Webhook-Logs (Standard: älter als 30 Tage).
    """
    try:
        if not os.path.exists(WEBHOOK_DB_PATH):
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_timestamp = cutoff_date.isoformat()
        
        with sqlite3.connect(WEBHOOK_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Zähle zuerst, wie viele gelöscht werden
            cursor.execute('SELECT COUNT(*) FROM webhook_logs WHERE timestamp < ?', (cutoff_timestamp,))
            count_to_delete = cursor.fetchone()[0]
            
            # Lösche alte Einträge
            cursor.execute('DELETE FROM webhook_logs WHERE timestamp < ?', (cutoff_timestamp,))
            conn.commit()
            
            if count_to_delete > 0:
                logger.info(f"🧹 {count_to_delete} alte Webhook-Logs gelöscht (älter als {days_to_keep} Tage)")
            
            return count_to_delete
            
    except Exception as e:
        logger.error(f"❌ Fehler beim Bereinigen alter Webhook-Logs: {e}")
        return 0

# Initialisiere Datenbank beim Import
if __name__ != "__main__":
    init_webhook_database()

# Test-Funktionen
if __name__ == "__main__":
    print("🧪 Teste Webhook Logger...")
    
    # Initialisiere DB
    success = init_webhook_database()
    print(f"Datenbank-Initialisierung: {'✅' if success else '❌'}")
    
    # Test-Logs erstellen
    test_success = log_webhook_request(
        webhook_type='nfc',
        url='http://192.168.1.100/axis-cgi/param.cgi',
        response_code=200,
        response_time_ms=150,
        success=True,
        trigger_source='nfc_reader',
        card_pan='4220560000002044'
    )
    print(f"Test-Log erstellt: {'✅' if test_success else '❌'}")
    
    # Logs abrufen
    logs = get_webhook_logs(limit=5)
    print(f"Logs abgerufen: {len(logs)} Einträge")
    
    # Statistiken
    stats = get_webhook_statistics(hours_back=24)
    print(f"Statistiken: {stats['total_requests']} Requests, {stats['success_rate']}% Erfolgsrate")
    
    print("✅ Test abgeschlossen")