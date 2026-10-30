import logging
import sys

from code_review.config import get_settings


def setup_logging() -> None:
    settings = get_settings()

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    already_has_console = any(
        isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
        for h in root_logger.handlers
    )
    if not already_has_console:
        root_logger.addHandler(console_handler)
