"""
Webhook Manager für NFC- und Barcode-Events
==========================================

Zentrale Verwaltung für Webhook-Aufrufe bei erfolgreichen Scans.
Unterstützt GET-Requests für Axis-Lautsprecher und andere HTTP-Geräte.
"""

import requests
import logging
import json
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Import des sicheren Webhook-Loggers
try:
    from .safe_logging import safe_log_webhook
    WEBHOOK_LOGGING_AVAILABLE = True
except ImportError:
    WEBHOOK_LOGGING_AVAILABLE = False
    def safe_log_webhook(*args, **kwargs):
        pass

# Konfigurationsdatei für Einstellungen
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def load_webhook_settings() -> Dict[str, Any]:
    """Lädt die Webhook-Einstellungen aus der Konfigurationsdatei."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                settings = json.load(f)
                # Preserve existing webhook_enabled state - don't override with default
                # Use existing value if present, otherwise keep previous state
                result = {
                    'webhook_enabled': settings.get('webhook_enabled', True),  # Default to True like in routes.py
                    'nfc_webhook_url': settings.get('nfc_webhook_url', '').strip(),
                    'barcode_webhook_url': settings.get('barcode_webhook_url', '').strip(),
                    'webhook_timeout': settings.get('webhook_timeout', 5),
                    'webhook_auth_type': settings.get('webhook_auth_type', 'none'),
                    'webhook_auth_user': settings.get('webhook_auth_user', '').strip(),
                    'webhook_auth_password': settings.get('webhook_auth_password', '').strip(),
                    'nfc_webhook_delay': settings.get('nfc_webhook_delay', 0.0),
                    'barcode_webhook_delay': settings.get('barcode_webhook_delay', 0.0)
                }
                logger.debug(f"Webhook settings loaded: enabled={result['webhook_enabled']}")
                return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error in Webhook-Konfiguration: {e}")
    except IOError as e:
        logger.error(f"IO Error beim Laden der Webhook-Konfiguration: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Laden der Webhook-Konfiguration: {e}")

    # Default settings - webhook_enabled should be True to match routes.py behavior
    # This ensures consistency across the application
    logger.warning("Using default webhook settings (enabled=True)")
    return {
        'webhook_enabled': True,  # Changed to True for consistency with routes.py
        'nfc_webhook_url': '',
        'barcode_webhook_url': '',
        'webhook_timeout': 5,
        'webhook_auth_type': 'none',
        'webhook_auth_user': '',
        'webhook_auth_password': '',
        'nfc_webhook_delay': 0.0,
        'barcode_webhook_delay': 0.0
    }

def trigger_webhook(webhook_type: str, data: Dict[str, Any], is_test: bool = False) -> bool:
    """
    Triggert einen Webhook-Aufruf.

    Args:
        webhook_type: 'nfc' oder 'barcode'
        data: Daten die gesendet werden sollen
        is_test: True wenn es ein Test-Aufruf ist

    Returns:
        bool: True wenn erfolgreich, False bei Fehler
    """
    settings = load_webhook_settings()

    # IMPORTANT: Webhook functionality is INDEPENDENT of "Allow All Barcodes" setting
    # These features must work simultaneously without conflict
    if not settings['webhook_enabled']:
        logger.debug("Webhooks sind deaktiviert")
        return False
    
    # Webhook-URL auswählen
    if webhook_type == 'nfc':
        webhook_url = settings['nfc_webhook_url']
    elif webhook_type == 'barcode':
        webhook_url = settings['barcode_webhook_url']
    else:
        logger.error(f"Unbekannter Webhook-Typ: {webhook_type}")
        return False
    
    if not webhook_url:
        logger.debug(f"Keine {webhook_type.upper()}-Webhook-URL konfiguriert")
        return False
    
    # Daten vorbereiten
    payload = {
        'type': webhook_type,
        'timestamp': datetime.now().isoformat(),
        'test': is_test,
        **data
    }
    
    try:
        import time  # Import time at the beginning of try block
        timeout = settings['webhook_timeout']

        # Delay anwenden falls konfiguriert
        delay_key = f'{webhook_type}_webhook_delay'
        delay = settings.get(delay_key, 0.0)
        if delay > 0 and not is_test:
            logger.debug(f"⏱️ Warte {delay} Sekunden vor {webhook_type.upper()}-Webhook")
            time.sleep(delay)
        
        # Authentifizierung vorbereiten
        auth = None
        auth_type = settings.get('webhook_auth_type', 'none')
        auth_user = settings.get('webhook_auth_user', '')
        auth_password = settings.get('webhook_auth_password', '')
        
        if auth_type != 'none' and auth_user and auth_password:
            if auth_type == 'basic':
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(auth_user, auth_password)
                logger.debug(f"🔐 Verwendung von HTTP Basic Auth für {webhook_type.upper()}-Webhook")
            elif auth_type == 'digest':
                from requests.auth import HTTPDigestAuth
                auth = HTTPDigestAuth(auth_user, auth_password)
                logger.debug(f"🔐 Verwendung von HTTP Digest Auth für {webhook_type.upper()}-Webhook")
        
        # GET-Request für maximale Kompatibilität (Axis-Lautsprecher etc.)
        logger.info(f"🌐 Triggering {webhook_type.upper()}-Webhook: {webhook_url}")
        
        start_time = time.time()
        
        response = requests.get(
            webhook_url,
            params=payload,
            timeout=timeout,
            headers={'User-Agent': 'Guard-System-Webhook/1.0'},
            auth=auth
        )
        
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Log the webhook request
        if WEBHOOK_LOGGING_AVAILABLE:
            safe_log_webhook(
                webhook_type=webhook_type,
                url=webhook_url,
                method='GET',
                payload=payload,
                response_code=response.status_code,
                response_time_ms=response_time_ms,
                success=response.status_code == 200,
                trigger_source='webhook_manager',
                card_pan=data.get('pan'),
                barcode_data=data.get('code')
            )
        
        if response.status_code == 200:
            logger.info(f"✅ {webhook_type.upper()}-Webhook erfolgreich ausgeführt: {response.status_code} ({response_time_ms}ms)")
            return True
        else:
            logger.warning(f"⚠️ {webhook_type.upper()}-Webhook nicht erfolgreich: HTTP {response.status_code} ({response_time_ms}ms)")
            return False
    
    except requests.exceptions.Timeout:
        error_message = f"Timeout nach {timeout}s"
        logger.error(f"❌ {webhook_type.upper()}-Webhook Timeout nach {timeout}s")
        
        # Log failed webhook
        if WEBHOOK_LOGGING_AVAILABLE:
            safe_log_webhook(
                webhook_type=webhook_type,
                url=webhook_url,
                method='GET',
                payload=payload,
                success=False,
                error_message=error_message,
                trigger_source='webhook_manager',
                card_pan=data.get('pan'),
                barcode_data=data.get('code')
            )
        return False
        
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        logger.error(f"❌ {webhook_type.upper()}-Webhook Fehler: {e}")
        
        # Log failed webhook
        if WEBHOOK_LOGGING_AVAILABLE:
            safe_log_webhook(
                webhook_type=webhook_type,
                url=webhook_url,
                method='GET',
                payload=payload,
                success=False,
                error_message=error_message,
                trigger_source='webhook_manager',
                card_pan=data.get('pan'),
                barcode_data=data.get('code')
            )
        return False
        
    except Exception as e:
        error_message = f"Unerwarteter Fehler: {str(e)}"
        logger.error(f"❌ Unerwarteter {webhook_type.upper()}-Webhook Fehler: {e}")
        
        # Log failed webhook
        if WEBHOOK_LOGGING_AVAILABLE:
            safe_log_webhook(
                webhook_type=webhook_type,
                url=webhook_url,
                method='GET',
                payload=payload,
                success=False,
                error_message=error_message,
                trigger_source='webhook_manager',
                card_pan=data.get('pan'),
                barcode_data=data.get('code')
            )
        return False

def trigger_nfc_webhook(card_data: Dict[str, Any], is_test: bool = False) -> bool:
    """
    Triggert einen NFC-Webhook bei erfolgreichem Kartenscan.
    
    Args:
        card_data: Dictionary mit Kartendaten (pan, card_type, etc.)
        is_test: True wenn es ein Test-Aufruf ist
    
    Returns:
        bool: True wenn erfolgreich
    """
    # Sichere Daten für Webhook (keine vollständige PAN)
    safe_data = {
        'card_id': card_data.get('pan', '')[-4:] if card_data.get('pan') else 'unknown',  # Nur letzte 4 Ziffern
        'card_type': card_data.get('card_type', 'unknown'),
        'status': card_data.get('status', 'unknown')
    }
    
    if not is_test:
        logger.info(f"🔔 NFC-Karte erkannt - Webhook wird ausgelöst")
    
    return trigger_webhook('nfc', safe_data, is_test)

def trigger_barcode_webhook(barcode_data: Dict[str, Any], is_test: bool = False) -> bool:
    """
    Triggert einen Barcode-Webhook bei erfolgreichem Scan.
    
    Args:
        barcode_data: Dictionary mit Barcode-Daten (code, status, etc.)
        is_test: True wenn es ein Test-Aufruf ist
    
    Returns:
        bool: True wenn erfolgreich
    """
    safe_data = {
        'code': barcode_data.get('code', 'unknown'),
        'status': barcode_data.get('status', 'unknown'),
        'scan_type': barcode_data.get('scan_type', 'barcode')
    }
    
    if not is_test:
        logger.info(f"🔔 Barcode gescannt - Webhook wird ausgelöst")
    
    return trigger_webhook('barcode', safe_data, is_test)

# Axis-Lautsprecher spezifische Funktionen
def trigger_axis_audio_clip(ip_address: str, audio_file: str = "Ansage.mp3", 
                           volume: int = 50, username: str = "root", 
                           password: str = "") -> bool:
    """
    Speziell für Axis-Lautsprecher optimierte Audio-Clip Funktion.
    
    Args:
        ip_address: IP-Adresse des Axis-Lautsprechers
        audio_file: Name der Audio-Datei
        volume: Lautstärke (0-100)
        username: Benutzername für Authentifizierung
        password: Passwort für Authentifizierung
    
    Returns:
        bool: True wenn erfolgreich
    """
    url = f"http://{ip_address}/axis-cgi/playclip.cgi"
    params = {
        "location": audio_file,
        "repeat": "0",
        "volume": str(volume),
        "audiodeviceid": "0",
        "audiooutputid": "0"
    }
    
    try:
        if username and password:
            from requests.auth import HTTPDigestAuth
            auth = HTTPDigestAuth(username, password)
        else:
            auth = None
        
        response = requests.get(url, params=params, auth=auth, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"🔊 Axis Audio-Clip erfolgreich gestartet auf {ip_address}")
            return True
        else:
            logger.warning(f"⚠️ Axis Audio-Clip fehlgeschlagen auf {ip_address}: HTTP {response.status_code}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Axis Audio-Clip Fehler auf {ip_address}: {e}")
        return False

# Export
__all__ = [
    'trigger_nfc_webhook',
    'trigger_barcode_webhook', 
    'trigger_webhook',
    'trigger_axis_audio_clip',
    'load_webhook_settings'
]