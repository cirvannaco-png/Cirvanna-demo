"""
StructuredLogger – JSON logging.
"""
import logging
import json
import datetime

class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'trace_id': getattr(record, 'trace_id', None),
                'span_id': getattr(record, 'span_id', None),
                'user_id': getattr(record, 'user_id', None),
                'shard_id': getattr(record, 'shard_id', None),
                'region': getattr(record, 'region', 'default')
            }
            if record.exc_info:
                log_record['exception'] = self.formatException(record.exc_info)
            return json.dumps(log_record)

    def info(self, message: str, **context):
        self.logger.info(message, extra={'extra': context})

    def warning(self, message: str, **context):
        self.logger.warning(message, extra={'extra': context})

    def error(self, message: str, exc_info=None, **context):
        self.logger.error(message, exc_info=exc_info, extra={'extra': context})
