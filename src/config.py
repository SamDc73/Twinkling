import os

import yaml
from dotenv import load_dotenv

from utils import get_logger


logger = get_logger(__name__)


def load_env_vars() -> None:
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
        raise ValueError(
            msg,
        )


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(config_path) as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.exception(f"Config file not found: {config_path}")
        raise
    except yaml.YAMLError as e:
        logger.exception(f"Error parsing config file: {e}")
        raise
