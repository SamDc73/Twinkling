import tweepy
import os
from utils import get_logger

logger = get_logger(__name__)


class TwitterPoster:
    def __init__(self):
        try:
            # Load credentials from environment variables
            ACCESS_KEY = os.getenv("TWITTER_ACCESS_TOKEN")
            ACCESS_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            CONSUMER_KEY = os.getenv("TWITTER_API_KEY")
            CONSUMER_SECRET = os.getenv("TWITTER_API_SECRET")
            BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

            # Authenticate to Twitter
            auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
            auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)

            # Create API object for v1.1 endpoints
            self.api = tweepy.API(auth)

            # Create Client object for v2 endpoints
            self.client = tweepy.Client(
                bearer_token=BEARER_TOKEN,
                access_token=ACCESS_KEY,
                access_token_secret=ACCESS_SECRET,
                consumer_key=CONSUMER_KEY,
                consumer_secret=CONSUMER_SECRET,
            )

            logger.info("Twitter API client initialized successfully")
        except Exception as e:
            logger.exception(f"Error initializing Twitter API client: {str(e)}")
            raise

    def post_tweet(self, content: str, image_path: str = None) -> bool:
        try:
            media_ids = None
            if image_path and os.path.exists(image_path):
                media = self.api.media_upload(image_path)
                media_ids = [media.media_id]

            response = self.client.create_tweet(text=content, media_ids=media_ids)
            logger.info(f"Tweet posted successfully. Tweet ID: {response.data['id']}")
            return True
        except tweepy.errors.TweepyException as e:
            logger.error(f"Error posting tweet: {str(e)}")
            logger.error(
                f"Error details: {e.api_errors if hasattr(e, 'api_errors') else 'No additional details'}"
            )
            return False

    def get_user_info(self) -> dict:
        try:
            response = self.client.get_me(user_fields=["id", "name", "username"])
            user = response.data
            logger.info(f"Retrieved user info for: @{user.username}")
            return user
        except tweepy.errors.TweepyException as e:
            logger.error(f"Error retrieving user info: {str(e)}")
            logger.error(
                f"Error details: {e.api_errors if hasattr(e, 'api_errors') else 'No additional details'}"
            )
            return None
