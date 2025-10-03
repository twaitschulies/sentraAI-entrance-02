import os
import json
import logging
import datetime
from logging.handlers import RotatingFileHandler
from app.config import LOG_LEVEL, MAX_LOG_ENTRIES
from typing import Dict, List, Optional, Any

# Konfiguriere den Standard-Logger
logger = logging.getLogger('SentraAI')
logger.setLevel(getattr(logging, LOG_LEVEL))

# Robuste Log-Konfiguration mit Fallback
try:
    # Erstelle Log-Verzeichnis falls es nicht existiert
    os.makedirs('logs', exist_ok=True)
    
    # Versuche Datei-Handler zu erstellen
    file_handler = RotatingFileHandler('logs/system.log', maxBytes=1024*1024*5, backupCount=5)
    file_handler.setLevel(getattr(logging, LOG_LEVEL))
    
    # Formatiere die Log-Nachrichten
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Füge den Handler zum Logger hinzu
    logger.addHandler(file_handler)
    
except (PermissionError, OSError) as e:
    # Fallback zu Console-Logging bei Problemen
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Warnung ausgeben
    logger.warning(f"Datei-Logging nicht möglich ({e}), verwende Console-Logging")
    logger.warning("Lösung: sudo chmod -R 777 logs/ && sudo chown -R $USER:$USER logs/")

# Erstelle einen Stream-Handler für die Konsole
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, LOG_LEVEL))
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Exportiere den Standard-Logger als system_logger
system_logger = logger

class Logger:
    """Protokolliert System- und Benutzeraktivitäten."""
    
    # Log-Level-Konstanten
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10
    
    # Level-Namen für die Anzeige
    _LEVEL_NAMES = {
        CRITICAL: "CRITICAL",
        ERROR: "ERROR",
        WARNING: "WARNING",
        INFO: "INFO",
        DEBUG: "DEBUG"
    }
    
    def __init__(self):
        """Initialisiert das Logger-Objekt."""
        self.logs = []
        self._log_file = os.path.join('logs', "app.log")
        
        # Erstelle Logs-Verzeichnis, falls es nicht existiert
        os.makedirs('logs', exist_ok=True)
        
        # Lade vorhandene Logs, wenn vorhanden
        self._load_logs()
    
    def _load_logs(self) -> None:
        """Lädt vorhandene Logs aus der Log-Datei."""
        try:
            if os.path.exists(self._log_file):
                with open(self._log_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        try:
                            self.logs = json.loads(content)
                        except json.JSONDecodeError as e:
                            print(f"JSON-Fehler beim Laden der Logs: {str(e)}")
                            # Versuche Log-Datei zu reparieren
                            self._repair_log_file()
                            self.logs = []
                    else:
                        self.logs = []
                # Begrenze die Anzahl der geladenen Logs
                if len(self.logs) > MAX_LOG_ENTRIES:
                    self.logs = self.logs[-MAX_LOG_ENTRIES:]
        except Exception as e:
            print(f"Fehler beim Laden der Logs: {str(e)}")
            self.logs = []
    
    def _repair_log_file(self) -> None:
        """Repariert eine beschädigte Log-Datei."""
        try:
            backup_file = self._log_file + '.corrupted.bak'
            # Erstelle Backup der beschädigten Datei
            if os.path.exists(self._log_file):
                os.rename(self._log_file, backup_file)
                print(f"Beschädigte Log-Datei gesichert als: {backup_file}")
            
            # Erstelle neue leere Log-Datei
            with open(self._log_file, 'w') as f:
                json.dump([], f)
            print("Neue leere Log-Datei erstellt")
            
        except Exception as e:
            print(f"Fehler beim Reparieren der Log-Datei: {str(e)}")
    
    def _save_logs(self) -> None:
        """Speichert Logs sicher in der Log-Datei."""
        try:
            # Verwende temporäre Datei für atomares Schreiben
            temp_file = self._log_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(self.logs, f, separators=(',', ':'))  # Kompakte JSON
            
            # Atomare Umbenennung für sicheres Speichern
            os.replace(temp_file, self._log_file)
        except Exception as e:
            print(f"Fehler beim Speichern der Logs: {str(e)}")
            # Cleanup der temporären Datei
            try:
                temp_file = self._log_file + '.tmp'
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
    
    def _log(self, level: int, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Erstellt einen Log-Eintrag.
        
        Args:
            level: Log-Level
            message: Log-Nachricht
            user: Benutzername (optional)
            data: Zusätzliche Daten zum Logging (optional)
        """
        # Konvertiere String LOG_LEVEL zu Integer für Vergleich
        min_level = getattr(self, LOG_LEVEL, self.INFO) if isinstance(LOG_LEVEL, str) else LOG_LEVEL
        if level < min_level:
            return
        
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "level": level,
            "level_name": self._LEVEL_NAMES.get(level, "UNKNOWN"),
            "message": message
        }
        
        if user:
            log_entry["user"] = user
            
        if data:
            log_entry["data"] = data
        
        self.logs.append(log_entry)
        
        # Begrenze die Anzahl der gespeicherten Logs
        if len(self.logs) > MAX_LOG_ENTRIES:
            self.logs = self.logs[-MAX_LOG_ENTRIES:]
            
        self._save_logs()
        
        # Bei kritischen Fehlern oder Fehlern immer auf der Konsole ausgeben
        if level >= self.ERROR:
            print(f"[{log_entry['level_name']}] {message}")
    
    def debug(self, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Protokolliert eine Debug-Nachricht."""
        self._log(self.DEBUG, message, user, data)
    
    def info(self, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Protokolliert eine Info-Nachricht."""
        self._log(self.INFO, message, user, data)
    
    def warning(self, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Protokolliert eine Warnungs-Nachricht."""
        self._log(self.WARNING, message, user, data)
    
    def error(self, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Protokolliert eine Fehler-Nachricht."""
        self._log(self.ERROR, message, user, data)
    
    def critical(self, message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Protokolliert einen kritischen Fehler."""
        self._log(self.CRITICAL, message, user, data)
    
    def get_logs(self, limit: int = 100, level: Optional[int] = None, user: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ruft gefilterte Logs ab.
        
        Args:
            limit: Maximale Anzahl der zurückzugebenden Logs
            level: Minimales Log-Level für die Filterung (optional)
            user: Nach diesem Benutzer filtern (optional)
            
        Returns:
            Eine Liste gefilterter Log-Einträge
        """
        filtered_logs = self.logs
        
        if level is not None:
            filtered_logs = [log for log in filtered_logs if log["level"] >= level]
            
        if user is not None:
            filtered_logs = [log for log in filtered_logs if log.get("user") == user]
            
        # Neueste Logs zuerst
        filtered_logs = sorted(filtered_logs, key=lambda x: x["timestamp"], reverse=True)
        
        return filtered_logs[:limit]
    
    def clear_logs(self) -> None:
        """Löscht alle Logs."""
        self.logs = []
        self._save_logs()

# Erstelle ein Singleton für globalen Zugriff auf den Logger
_logger = Logger()

# Einfache Funktionen für den Zugriff auf den Logger
def log_debug(message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert eine Debug-Nachricht."""
    _logger.debug(message, user, data)

def log_info(message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert eine Info-Nachricht."""
    _logger.info(message, user, data)

def log_warning(message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert eine Warnungs-Nachricht."""
    _logger.warning(message, user, data)

def log_error(message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert eine Fehler-Nachricht."""
    _logger.error(message, user, data)

def log_critical(message: str, user: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert einen kritischen Fehler."""
    _logger.critical(message, user, data)

def log_system(message: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Protokolliert eine System-Nachricht."""
    _logger.info(f"SYSTEM: {message}", None, data)

def get_logs(limit: int = 100, level: Optional[int] = None, user: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ruft gefilterte Logs ab."""
    return _logger.get_logs(limit, level, user)

def clear_logs() -> None:
    """Löscht alle Logs."""
    _logger.clear_logs()

class LogManager:
    """Verwaltet System-Logs für die Benutzeroberfläche."""
    
    def __init__(self):
        self.log_file = 'logs/ui_logs.json'
        self.ensure_log_file_exists()
    
    def ensure_log_file_exists(self):
        """Stellt sicher, dass die Log-Datei existiert."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                json.dump({"logs": []}, f, separators=(',', ':'))
    
    def add_log(self, log_type, message, details=None):
        """Fügt einen neuen Log-Eintrag hinzu."""
        logs = self.get_logs()
        
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "type": log_type,
            "message": message,
            "details": details or {}
        }
        
        # Füge neuen Log an den Anfang der Liste
        logs.insert(0, log_entry)
        
        # Begrenze die Anzahl der Logs
        if len(logs) > MAX_LOG_ENTRIES:
            logs = logs[:MAX_LOG_ENTRIES]
        
        # Speichere Logs
        self.save_logs(logs)
        
        # Protokolliere den Eintrag auch im System-Logger
        level = getattr(logging, log_type.upper(), logging.INFO)
        system_logger.log(level, message)
        
        return log_entry
    
    def get_logs(self, log_type=None, limit=100):
        """Lädt alle Log-Einträge, optional gefiltert nach Typ."""
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
                logs = data.get("logs", [])
                
                if log_type:
                    logs = [log for log in logs if log["type"] == log_type]
                
                return logs[:limit]
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def save_logs(self, logs):
        """Speichert Logs in der Datei."""
        with open(self.log_file, 'w') as f:
            json.dump({"logs": logs}, f, indent=4)
    
    def clear_logs(self):
        """Löscht alle Logs."""
        self.save_logs([])
        return True

# Erstelle eine globale Instanz zur Verwendung in der Anwendung
log_manager = LogManager()

# Definiere Hilfsfunktionen für häufige Log-Typen
def log_scan(barcode, result, details=None):
    """Protokolliert einen Scan-Vorgang."""
    return log_manager.add_log("info", f"Barcode gescannt: {barcode}", {
        "barcode": barcode,
        "result": result,
        **(details or {})
    })

def log_system(message, details=None):
    """Protokolliert eine System-Nachricht."""
    return log_manager.add_log("system", message, details)

def log_user_action(username, action, details=None):
    """Protokolliert eine Benutzeraktion."""
    return log_manager.add_log("user", f"{username}: {action}", {
        "username": username,
        "action": action,
        **(details or {})
    }) 