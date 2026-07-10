"""
backend/core/logger_config.py
Comprehensive Logging Configuration
Structured logging with multiple handlers
"""

import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime
import json


class StructuredFormatter(logging.Formatter):
    """Structured JSON logging formatter"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'endpoint'):
            log_data['endpoint'] = record.endpoint
        
        return json.dumps(log_data)


class PlainFormatter(logging.Formatter):
    """Plain text logging formatter"""
    
    FORMAT = (
        '[%(asctime)s] [%(name)s:%(lineno)d] '
        '[%(levelname)s] %(message)s'
    )
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as plain text"""
        return super().format(record)


def setup_logging():
    """Configure logging system"""
    
    # Create logs directory
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Get log level from environment
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler (plain text)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(PlainFormatter())
    root_logger.addHandler(console_handler)
    
    # File handler - All logs (JSON)
    all_logs_handler = logging.handlers.RotatingFileHandler(
        logs_dir / 'all.log',
        maxBytes=10_000_000,  # 10 MB
        backupCount=10
    )
    all_logs_handler.setLevel(logging.DEBUG)
    all_logs_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(all_logs_handler)
    
    # File handler - Errors only
    error_handler = logging.handlers.RotatingFileHandler(
        logs_dir / 'errors.log',
        maxBytes=10_000_000,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(error_handler)
    
    # File handler - Trading logs
    trading_handler = logging.handlers.RotatingFileHandler(
        logs_dir / 'trading.log',
        maxBytes=50_000_000,  # 50 MB
        backupCount=20
    )
    trading_handler.setLevel(logging.INFO)
    trading_handler.setFormatter(StructuredFormatter())
    
    # Only log trading-related messages to trading.log
    trading_logger = logging.getLogger('backend.trading')
    trading_logger.addHandler(trading_handler)
    
    # File handler - Security logs
    security_handler = logging.handlers.RotatingFileHandler(
        logs_dir / 'security.log',
        maxBytes=10_000_000,
        backupCount=10
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(StructuredFormatter())
    
    security_logger = logging.getLogger('backend.security')
    security_logger.addHandler(security_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    # Log initialization
    root_logger.info('=' * 80)
    root_logger.info('Logging system initialized')
    root_logger.info('Log Level: %s', log_level)
    root_logger.info('Log Directory: %s', logs_dir.absolute())
    root_logger.info('=' * 80)


class LogContext:
    """Context manager for adding request context to logs"""
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.logger = logging.getLogger()
    
    def __enter__(self):
        """Enter context - set extra fields"""
        for key, value in self.context.items():
            for handler in self.logger.handlers:
                if isinstance(handler, logging.LoggerAdapter):
                    handler.extra[key] = value
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - clear extra fields"""
        for handler in self.logger.handlers:
            if isinstance(handler, logging.LoggerAdapter):
                for key in self.context:
                    handler.extra.pop(key, None)


class RequestContextLogger:
    """Logger with request context"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.context = {}
    
    def set_context(self, **kwargs):
        """Set request context"""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear request context"""
        self.context.clear()
    
    def info(self, msg: str, *args, **kwargs):
        """Log info with context"""
        self._log(logging.INFO, msg, args, kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning with context"""
        self._log(logging.WARNING, msg, args, kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error with context"""
        self._log(logging.ERROR, msg, args, kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug with context"""
        self._log(logging.DEBUG, msg, args, kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with context"""
        self._log(logging.ERROR, msg, args, kwargs, exc_info=True)
    
    def _log(self, level: int, msg: str, args, kwargs, exc_info=False):
        """Internal log method with context"""
        record = self.logger.makeRecord(
            self.logger.name,
            level,
            '',
            0,
            msg % args if args else msg,
            (),
            exc_info=exc_info
        )
        
        # Add context to record
        for key, value in self.context.items():
            setattr(record, key, value)
        
        self.logger.handle(record)


# Initialize logging on import
setup_logging()

# Export loggers
app_logger = logging.getLogger('backend.app')
trading_logger = logging.getLogger('backend.trading')
security_logger = logging.getLogger('backend.security')
database_logger = logging.getLogger('backend.database')
