from model_manager import ModelManager
from utils import get_logger


class ContentGenerator:
    def __init__(self, model_manager: ModelManager, prompts: dict) -> None:
        self.model_manager = model_manager
        self.prompts = prompts
        self.logger = get_logger(__name__)

    def generate_tweet(self, note_content: str) -> str:
        prompt = self.prompts["tweet_generation"].format(note_content=note_content)
        self.logger.info(f"Generating tweet with prompt: {prompt[:50]}...")
        tweet = self.model_manager.generate_content(prompt)
        if tweet is None:
            self.logger.warning("Failed to generate tweet content")
        return tweet
