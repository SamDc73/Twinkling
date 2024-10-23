import logging
import os
from datetime import datetime
from typing import Literal


# Suppress litellm debug messages
logging.getLogger("litellm").setLevel(logging.WARNING)


def setup_logging(verbose: bool = False, quiet: bool = False) -> logging.Logger:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"social_media_agent_{timestamp}.log")

    # Define log levels
    file_level = logging.DEBUG
    console_level: Literal["DEBUG", "INFO", "ERROR"] = (
        "ERROR" if quiet else "DEBUG" if verbose else "INFO"
    )

    # Create a custom logger
    logger = logging.getLogger("social_media_agent")
    logger.setLevel(logging.DEBUG)

    # Create handlers
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(file_level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level))

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
    return logging.getLogger(name)
