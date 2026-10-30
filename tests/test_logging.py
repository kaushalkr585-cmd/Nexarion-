import logging

from code_review.config import get_settings
from code_review.logging_setup import setup_logging


class TestLoggingSetup:
    def setup_method(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        get_settings.cache_clear()

    def test_setup_logging_does_not_crash(self) -> None:
        setup_logging()

    def test_root_logger_has_handler_after_setup(self) -> None:
        setup_logging()
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) >= 1

    def test_no_duplicate_handlers_on_repeated_calls(self) -> None:
        import sys

        setup_logging()
        setup_logging()
        root_logger = logging.getLogger()

        our_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
        ]
        assert len(our_handlers) == 1

    def test_logger_level_matches_settings(self) -> None:
        setup_logging()
        settings = get_settings()
        root_logger = logging.getLogger()
        expected_level = getattr(logging, settings.log_level)
        assert root_logger.level == expected_level
