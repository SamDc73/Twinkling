import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


# Suppress litellm debug messages
logging.getLogger("litellm").setLevel(logging.WARNING)


LoggingMode = Literal["normal", "verbose", "quiet"]


def setup_logging(*, mode: LoggingMode = "normal") -> logging.Logger:
    """Set up logging configuration.

    Parameters
    ----------
    mode : Literal["normal", "verbose", "quiet"], optional
        Logging mode to use, by default "normal"

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"social_media_agent_{timestamp}.log"

    # Define log levels
    file_level = logging.DEBUG
    console_level = {
        "quiet": logging.ERROR,
        "normal": logging.INFO,
        "verbose": logging.DEBUG,
    }[mode]

    # Create a custom logger
    logger = logging.getLogger("social_media_agent")
    logger.setLevel(logging.DEBUG)

    # Create handlers
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(file_level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)

    # Create formatters and add it to handlers
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    console_format = logging.Formatter("%(levelname)s: %(message)s")
    file_handler.setFormatter(file_format)
    console_handler.setFormatter(console_format)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "social_media_agent") -> logging.Logger:
    """Get a logger instance.

    Parameters
    ----------
    name : str, optional
        Name of the logger, by default "social_media_agent"

    Returns
    -------
    logging.Logger
        Logger instance.
    """
    return logging.getLogger(name)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Social media post generator")

    # Platform group
    platform_group = parser.add_mutually_exclusive_group()
    platform_group.add_argument(
        "--platform",
        nargs="+",
        choices=["twitter", "bluesky"],
        help="One or more platforms to post to (e.g., --platform twitter bluesky)",
    )
    platform_group.add_argument(
        "--all",
        action="store_true",
        help="Post to all available platforms",
    )

    parser.add_argument(
        "--sync-kb",
        action="store_true",
        help="Synchronize knowledge base with notes (initialize if needed)",
    )

    return parser.parse_args()
