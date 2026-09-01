import logging
import sys

import structlog


def _rename_level_to_severity(
    logger: object, method_name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    """Rename structlog's `level` key to `severity`, as expected by GCP Cloud Logging."""
    event_dict["severity"] = event_dict.pop("level", method_name).upper()
    return event_dict


def configure_logging(log_format: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)

    if log_format == "json":
        # GCP Cloud Logging parses single-line JSON written to stdout/stderr,
        # picking up `severity`, `message`, and `time` as special fields.
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.dev.set_exc_info,
                structlog.processors.TimeStamper(fmt="iso", utc=True, key="time"),
                structlog.processors.EventRenamer("message"),
                _rename_level_to_severity,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        )
    else:
        # In stdio mode, stdout carries the JSON-RPC stream; logs must go to stderr.
        structlog.configure(
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        )
