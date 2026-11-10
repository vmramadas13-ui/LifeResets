"""Application logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Set a concise standard log format without logging request contents."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
