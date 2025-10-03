"""
Unified Logging System for SentraAI Entrance Access Control
This consolidates all logging into a single, efficient system.
"""

import os
import json
import logging
import datetime
import traceback
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Any
from threading import Lock

# Thread safety for file operations
log_lock = Lock()

class UnifiedLogger:
    """Centralized logger with deduplication and meaningful context."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the unified logger only once."""
        if UnifiedLogger._initialized:
            return

        UnifiedLogger._initialized = True

        # Create logs directory
        self.log_dir = 'logs'
        os.makedirs(self.log_dir, exist_ok=True)

        # Configure root logger to prevent duplicate console outputs
        root_logger = logging.getLogger()
        root_logger.handlers.clear()  # Remove any existing handlers

        # Setup main logger
        self.logger = logging.getLogger('GuardSystem')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Don't propagate to root logger

        # Clear any existing handlers to prevent duplicates
        self.logger.handlers.clear()

        # Single rotating file handler
        self.setup_file_handler()

        # Single console handler
        self.setup_console_handler()

        # Deduplication cache (stores hash of recent messages)
        self.recent_messages = []
        self.max_cache_size = 100

        # JSON log storage for UI
        self.json_log_file = os.path.join(self.log_dir, 'app.log')
        self.json_logs = []
        self.load_json_logs()

    def setup_file_handler(self):
        """Setup single file handler with rotation."""
        try:
            file_handler = RotatingFileHandler(
                os.path.join(self.log_dir, 'system.log'),
                maxBytes=5*1024*1024,  # 5MB
                backupCount=3
            )
            file_handler.setLevel(logging.DEBUG)

            # Detailed formatter with context
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        except (PermissionError, OSError) as e:
            print(f"Warning: Could not create file handler: {e}")

    def setup_console_handler(self):
        """Setup single console handler."""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Simpler console format
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def is_duplicate(self, message: str, level: str) -> bool:
        """Check if this message was recently logged to prevent duplicates."""
        # Create a simple hash of the message + level
        msg_hash = f"{level}:{message}"

        if msg_hash in self.recent_messages:
            return True

        # Add to cache
        self.recent_messages.append(msg_hash)

        # Keep cache size limited
        if len(self.recent_messages) > self.max_cache_size:
            self.recent_messages.pop(0)

        return False

    def log(self, level: str, message: str, extra_context: Dict[str, Any] = None,
            exc_info: bool = False, dedupe: bool = True) -> None:
        """
        Main logging method with deduplication and context.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            extra_context: Additional context data
            exc_info: Include exception traceback if True
            dedupe: Check for duplicate messages if True
        """
        # Check for duplicates
        if dedupe and self.is_duplicate(message, level):
            return

        # Add extra context to message if provided
        if extra_context:
            context_str = ' | '.join([f"{k}={v}" for k, v in extra_context.items()])
            full_message = f"{message} | Context: {context_str}"
        else:
            full_message = message

        # Get the appropriate logging method
        log_method = getattr(self.logger, level.lower(), self.logger.info)

        # Log with exception info if needed
        if exc_info and level.upper() in ['ERROR', 'CRITICAL']:
            log_method(full_message, exc_info=True)
        else:
            log_method(full_message)

        # Also save to JSON for UI
        self.save_to_json(level, message, extra_context, exc_info)

    def save_to_json(self, level: str, message: str,
                     extra_context: Dict[str, Any] = None,
                     exc_info: bool = False) -> None:
        """Save log entry to JSON file for UI display."""
        with log_lock:
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "level": level.upper(),
                "message": message,
                "context": extra_context or {}
            }

            # Add traceback if error with exc_info
            if exc_info and level.upper() in ['ERROR', 'CRITICAL']:
                log_entry["traceback"] = traceback.format_exc()

            self.json_logs.append(log_entry)

            # Keep only last 1000 entries
            if len(self.json_logs) > 1000:
                self.json_logs = self.json_logs[-1000:]

            # Save to file
            try:
                with open(self.json_log_file, 'w') as f:
                    json.dump(self.json_logs, f, separators=(',', ':'))
            except Exception as e:
                self.logger.error(f"Failed to save JSON log: {e}")

    def load_json_logs(self) -> None:
        """Load existing JSON logs from file."""
        try:
            if os.path.exists(self.json_log_file):
                with open(self.json_log_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        self.json_logs = json.loads(content)
                    else:
                        self.json_logs = []
        except Exception as e:
            self.logger.error(f"Failed to load JSON logs: {e}")
            self.json_logs = []

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.log('DEBUG', message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.log('INFO', message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.log('WARNING', message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.log('ERROR', message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self.log('CRITICAL', message, **kwargs)

    def get_logs(self, limit: int = 100, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent logs for UI display."""
        logs = self.json_logs.copy()

        # Filter by level if specified
        if level:
            logs = [log for log in logs if log.get('level') == level.upper()]

        # Return most recent first
        logs.reverse()

        return logs[:limit]

    def clear_logs(self) -> None:
        """Clear all logs."""
        with log_lock:
            self.json_logs = []
            try:
                with open(self.json_log_file, 'w') as f:
                    json.dump([], f)
            except Exception as e:
                self.logger.error(f"Failed to clear logs: {e}")

# Create singleton instance
unified_logger = UnifiedLogger()

# Convenience functions for backward compatibility
def log_debug(message: str, **kwargs) -> None:
    unified_logger.debug(message, **kwargs)

def log_info(message: str, **kwargs) -> None:
    unified_logger.info(message, **kwargs)

def log_warning(message: str, **kwargs) -> None:
    unified_logger.warning(message, **kwargs)

def log_error(message: str, **kwargs) -> None:
    unified_logger.error(message, **kwargs)

def log_critical(message: str, **kwargs) -> None:
    unified_logger.critical(message, **kwargs)

def log_system(message: str, **kwargs) -> None:
    """Log system message."""
    unified_logger.info(f"[SYSTEM] {message}", **kwargs)

def log_nfc(message: str, pan: str = None, card_type: str = None, **kwargs) -> None:
    """Log NFC-related events with context."""
    context = kwargs.get('extra_context', {})
    if pan:
        context['pan'] = pan[-4:] if len(pan) > 4 else pan  # Only last 4 digits
    if card_type:
        context['card_type'] = card_type
    kwargs['extra_context'] = context
    unified_logger.info(f"[NFC] {message}", **kwargs)

def log_door(message: str, action: str = None, **kwargs) -> None:
    """Log door control events."""
    context = kwargs.get('extra_context', {})
    if action:
        context['action'] = action
    kwargs['extra_context'] = context
    unified_logger.info(f"[DOOR] {message}", **kwargs)

def log_auth(message: str, username: str = None, **kwargs) -> None:
    """Log authentication events."""
    context = kwargs.get('extra_context', {})
    if username:
        context['user'] = username
    kwargs['extra_context'] = context
    unified_logger.info(f"[AUTH] {message}", **kwargs)

def log_webhook(message: str, url: str = None, status_code: int = None, **kwargs) -> None:
    """Log webhook events."""
    context = kwargs.get('extra_context', {})
    if url:
        context['url'] = url
    if status_code:
        context['status_code'] = status_code
    kwargs['extra_context'] = context
    unified_logger.info(f"[WEBHOOK] {message}", **kwargs)

# Override standard Python loggers to use our unified system
def setup_module_loggers():
    """Configure all module loggers to use unified formatting."""
    modules = [
        'app.nfc_reader',
        'app.scanner',
        'app.routes',
        'app.gpio_control',
        'app.auth',
        'app.webhook_manager'
    ]

    for module_name in modules:
        module_logger = logging.getLogger(module_name)
        module_logger.handlers.clear()
        module_logger.propagate = False

        # Add our handlers
        for handler in unified_logger.logger.handlers:
            module_logger.addHandler(handler)

        module_logger.setLevel(logging.DEBUG)

# Setup module loggers on import
setup_module_loggers()

# Export main logger for direct use
logger = unified_logger