import os
from pathlib import Path
from typing import Any

import tweepy

from utils import get_logger


logger = get_logger(__name__)


class TwitterPoster:
    """Handler for posting content to Twitter."""

    def __init__(self) -> None:
        """Initialize Twitter API client with credentials from environment."""
        try:
            # Load credentials from environment variables
            access_key = os.getenv("TWITTER_ACCESS_TOKEN")
            access_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            consumer_key = os.getenv("TWITTER_API_KEY")
            consumer_secret = os.getenv("TWITTER_API_SECRET")
            bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

            # Authenticate to Twitter
            auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            auth.set_access_token(access_key, access_secret)

            # Create API object for v1.1 endpoints
            self.api = tweepy.API(auth)

            # Create Client object for v2 endpoints
            self.client = tweepy.Client(
                bearer_token=bearer_token,
                access_token=access_key,
                access_token_secret=access_secret,
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
            )
        except Exception:
            logger.exception("Error initializing Twitter API client")
            raise
        else:
            logger.info("Twitter API client initialized successfully")

    def post_tweet(self, content: str, image_path: str | None = None) -> bool:
        """Post a tweet, optionally with an image.

        Parameters
        ----------
        content : str
            The text content of the tweet.
        image_path : str | None, optional
            Path to an image file to attach, by default None.

        Returns
        -------
        bool
            True if tweet was posted successfully, False otherwise.
        """
        try:
            media_ids = None
            if image_path and Path(image_path).exists():
                media = self.api.media_upload(image_path)
                media_ids = [media.media_id]

            response = self.client.create_tweet(text=content, media_ids=media_ids)
        except tweepy.errors.TweepyException as exc:
            logger.exception("Error posting tweet")
            if hasattr(exc, "api_errors"):
                logger.exception("API error details: %s", exc.api_errors)
            return False
        else:
            logger.info("Tweet posted successfully. Tweet ID: %s", response.data["id"])
            return True

    def get_user_info(self) -> dict[str, Any] | None:
        """Get information about the authenticated user.

        Returns
        -------
        dict[str, Any] | None
            User information if successful, None otherwise.
        """
        try:
            response = self.client.get_me(user_fields=["id", "name", "username"])
            user = response.data
        except tweepy.errors.TweepyException as exc:
            logger.exception("Error retrieving user info")
            if hasattr(exc, "api_errors"):
                logger.exception("API error details: %s", exc.api_errors)
            return None
        else:
            logger.info("Retrieved user info for: @%s", user.username)
            return user
