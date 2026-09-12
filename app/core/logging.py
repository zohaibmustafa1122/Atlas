"""Application-wide logging configuration."""

import logging
import sys

from app.core.config import get_settings

_configured = False


def setup_logging() -> None:
    """Configure the root logger once, based on settings.log_level."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger, ensuring logging is configured first."""
    setup_logging()
    return logging.getLogger(name)
