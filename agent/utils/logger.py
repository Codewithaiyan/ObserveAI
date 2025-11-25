"""
Structured logging utility
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict


class StructuredLogger:
    """Structured JSON logger"""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Console handler with JSON formatter
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self._json_formatter())
        self.logger.addHandler(handler)
    
    def _json_formatter(self):
        """Create JSON formatter"""
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                }
                
                # Add extra fields if present
                if hasattr(record, 'extra'):
                    log_data.update(record.extra)
                
                return json.dumps(log_data)
        
        return JsonFormatter()
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        extra = {"extra": kwargs} if kwargs else {}
        self.logger.info(message, extra=extra)
    
    def error(self, message: str, **kwargs):
        """Log error message"""
        extra = {"extra": kwargs} if kwargs else {}
        self.logger.error(message, extra=extra)
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        extra = {"extra": kwargs} if kwargs else {}
        self.logger.warning(message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        extra = {"extra": kwargs} if kwargs else {}
        self.logger.debug(message, extra=extra)


# Global logger instance
logger = StructuredLogger("observeai-agent")
