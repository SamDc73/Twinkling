import os

from atproto import Client

from utils import get_logger


logger = get_logger(__name__)


class BlueskyPoster:
    """Handler for posting content to Bluesky."""

    def __init__(self) -> None:
        """Initialize Bluesky API client with credentials from environment."""
        try:
            # Load credentials from environment variables
            self.username = os.getenv("BLUESKY_USERNAME")
            self.password = os.getenv("BLUESKY_PASSWORD")

            if not self.username or not self.password:
                raise ValueError("BLUESKY_USERNAME and BLUESKY_PASSWORD are required")

            # Create client and login
            self.client = Client()
            self.client.login(self.username, self.password)

        except Exception:
            logger.exception("Error initializing Bluesky API client")
            raise
        else:
            logger.info("Bluesky API client initialized successfully")

    def post_tweet(self, content: str, image_path: str | None = None) -> bool:
        """Post to Bluesky, optionally with an image."""
        try:
            # Add more detailed logging
            logger.info("Attempting to post to Bluesky: %s...", content[:50])

            response = self.client.send_post(text=content)

            # Log the response
            logger.info("Bluesky API response: %s", response)

            if not response:
                logger.error("Empty response from Bluesky API")
                return False

            return True

        except Exception as e:
            logger.exception("Error posting to Bluesky: %s", str(e))
            return False
