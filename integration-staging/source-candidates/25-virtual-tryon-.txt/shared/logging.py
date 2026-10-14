import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any
from pythonjsonlogger import jsonlogger

class CirvannaJSONFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging"""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any]
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['level'] = record.levelname
        log_record['service'] = getattr(record, 'service', 'unknown')
        log_record['environment'] = getattr(record, 'environment', 'development')
        if hasattr(record, 'trace_id'):
            log_record['trace_id'] = record.trace_id

        # Remove unnecessary fields
        for field in ['filename', 'module', 'funcName', 'lineno',
                      'msecs', 'relativeCreated', 'process', 'thread']:
            log_record.pop(field, None)

def setup_logging(
    service_name: str,
    log_level: str = "INFO",
    json_format: bool = True
) -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        formatter = CirvannaJSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Add service name to all logs
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = service_name
        return record

    logging.setLogRecordFactory(record_factory)

    return logger
