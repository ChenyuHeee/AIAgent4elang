import json
import logging
import pathlib
from datetime import datetime
from typing import Any, Dict

_LOGGERS: Dict[str, logging.Logger] = {}


def _json_formatter(record: logging.LogRecord) -> str:
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": record.levelname,
        "name": record.name,
        "message": record.getMessage(),
    }
    if record.exc_info:
        payload["exception"] = logging.Formatter().formatException(record.exc_info)
    return json.dumps(payload, ensure_ascii=False)


def setup_logger(name: str, log_dir: str) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]

    pathlib.Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stream_handler)

    file_path = pathlib.Path(log_dir) / f"{name}.log"
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)

    def emit_json(record: logging.LogRecord) -> str:
        return _json_formatter(record)

    logger.emit_json = emit_json  # type: ignore[attr-defined]

    _LOGGERS[name] = logger
    return logger


def log_struct(logger: logging.Logger, event: str, **kwargs: Any) -> None:
    payload = {"event": event, **kwargs}
    logger.info(json.dumps(payload, ensure_ascii=False))
