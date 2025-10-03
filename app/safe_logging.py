"""
Safe Logging Module
===================
Sichere Wrapper für alle Logging-Funktionen.
Gewährleistet, dass bestehende Funktionen nie beeinträchtigt werden.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Import der bestehenden Logger-Module
try:
    from . import error_logger
    ERROR_LOGGER_AVAILABLE = True
except ImportError:
    ERROR_LOGGER_AVAILABLE = False
    logger.warning("error_logger nicht verfügbar")

try:
    from .webhook_logger import log_webhook_request, get_webhook_logs, get_webhook_statistics
    WEBHOOK_LOGGER_AVAILABLE = True
except ImportError:
    WEBHOOK_LOGGER_AVAILABLE = False
    logger.warning("webhook_logger nicht verfügbar")

try:
    from .structured_fallback_log import log_structured_fallback
    STRUCTURED_LOGGER_AVAILABLE = True
except ImportError:
    STRUCTURED_LOGGER_AVAILABLE = False
    logger.warning("structured_fallback_log nicht verfügbar")

def safe_log_fallback(raw_data: str, error_type: str) -> bool:
    """
    Sichere Fallback-Logging-Funktion.
    Versucht zuerst strukturiertes Logging, fällt auf Standard zurück.
    """
    try:
        # Versuche strukturiertes Logging
        if STRUCTURED_LOGGER_AVAILABLE:
            try:
                result = log_structured_fallback(raw_data, error_type)
                if result:
                    return True
            except Exception as e:
                logger.debug(f"Strukturiertes Logging fehlgeschlagen: {e}")
        
        # Fallback auf Standard error_logger
        if ERROR_LOGGER_AVAILABLE:
            try:
                return error_logger.log_fallback(raw_data, error_type)
            except Exception as e:
                logger.error(f"Standard-Logging fehlgeschlagen: {e}")
        
        # Letzter Fallback: Nur console logging
        logger.error(f"Fallback-Log: {error_type} - {raw_data[:100]}...")
        return False
        
    except Exception as e:
        logger.error(f"Alle Logging-Methoden fehlgeschlagen: {e}")
        return False

def safe_log_webhook(
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
    Sichere Webhook-Logging-Funktion.
    """
    try:
        if WEBHOOK_LOGGER_AVAILABLE:
            return log_webhook_request(
                webhook_type=webhook_type,
                url=url,
                method=method,
                payload=payload,
                response_code=response_code,
                response_time_ms=response_time_ms,
                success=success,
                error_message=error_message,
                trigger_source=trigger_source,
                card_pan=card_pan,
                barcode_data=barcode_data
            )
        else:
            # Fallback: Console-Logging
            status = "✅" if success else "❌"
            logger.info(f"🔗 Webhook {status}: {webhook_type} -> {url} ({response_code})")
            return True
    except Exception as e:
        logger.error(f"Webhook-Logging fehlgeschlagen: {e}")
        return False

def safe_get_fallback_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Sichere Funktion zum Abrufen von Fallback-Logs.
    """
    try:
        if ERROR_LOGGER_AVAILABLE:
            return error_logger.get_fallback_logs(limit=limit)
        else:
            return []
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Fallback-Logs: {e}")
        return []

def safe_get_webhook_logs(limit: int = 50, webhook_type: str = None) -> List[Dict[str, Any]]:
    """
    Sichere Funktion zum Abrufen von Webhook-Logs.
    """
    try:
        if WEBHOOK_LOGGER_AVAILABLE:
            return get_webhook_logs(limit=limit, webhook_type=webhook_type)
        else:
            return []
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Webhook-Logs: {e}")
        return []

def safe_get_webhook_stats(hours_back: int = 24) -> Dict[str, Any]:
    """
    Sichere Funktion zum Abrufen von Webhook-Statistiken.
    """
    try:
        if WEBHOOK_LOGGER_AVAILABLE:
            return get_webhook_statistics(hours_back=hours_back)
        else:
            return {'total_requests': 0, 'error': 'Webhook-Logger nicht verfügbar'}
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Webhook-Statistiken: {e}")
        return {'error': str(e)}

def get_logging_status() -> Dict[str, Any]:
    """
    Gibt den Status aller Logging-Module zurück.
    """
    return {
        'error_logger_available': ERROR_LOGGER_AVAILABLE,
        'webhook_logger_available': WEBHOOK_LOGGER_AVAILABLE,
        'structured_logger_available': STRUCTURED_LOGGER_AVAILABLE,
        'safe_mode': True
    }

# Test-Funktion
if __name__ == "__main__":
    print("🧪 Safe Logging Tests")
    print("=" * 50)
    
    # Status prüfen
    status = get_logging_status()
    print("Logger Status:")
    for key, value in status.items():
        print(f"  {key}: {'✅' if value else '❌'}")
    
    # Test Fallback-Logging
    print("\nTest Fallback-Logging:")
    result = safe_log_fallback("Test-Daten für Fallback", "test_error")
    print(f"Fallback-Log: {'✅' if result else '❌'}")
    
    # Test Webhook-Logging
    print("\nTest Webhook-Logging:")
    result = safe_log_webhook(
        webhook_type="test",
        url="http://example.com",
        response_code=200,
        success=True
    )
    print(f"Webhook-Log: {'✅' if result else '❌'}")
    
    print("\n✅ Tests abgeschlossen")