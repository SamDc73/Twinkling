import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from utils import get_logger


logger = get_logger(__name__)


def load_env_vars() -> None:
    """Load environment variables from .env file and validate required vars exist."""
    load_dotenv()

    required_vars = [
        "SAMBANOVA_API_KEY",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET",
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_BEARER_TOKEN",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        raise ValueError(msg)


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file.

    Returns
    -------
    dict[str, Any]
        The loaded configuration dictionary.

    Raises
    ------
    FileNotFoundError
        If the config file cannot be found.
    yaml.YAMLError
        If the config file cannot be parsed.
    """
    config_path = Path(__file__).parent.parent / "config.yaml"
    try:
        with config_path.open() as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.exception("Config file not found: %s", config_path)
        raise
    except yaml.YAMLError:
        logger.exception("Error parsing config file")
        raise
